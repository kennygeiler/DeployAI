"""Internal API: drain + introspect the synthesis-refresh job queue.

Drain runs Phase 0.5's compounding-synthesis workers against pending
``synthesis_refresh_jobs`` rows. Lives behind the same X-DeployAI-Internal-Key
header as the other ``/internal/v1/admin/...`` routes. Phase 0.6 swaps the
manual drain for a cron worker; this endpoint stays for forced-drain support
in tests + incident response.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.canonical_memory.matrix import SynthesisRefreshJob
from control_plane.workers.synthesizer import (
    refresh_decision_provenance,
    refresh_risk_explainer,
    refresh_stakeholder_brief,
)

router = APIRouter(prefix="/admin/synthesis", tags=["internal-synthesis"])

_DEFAULT_LIMIT = 25
_MAX_LIMIT = 200


class DrainResult(BaseModel):
    processed: int
    succeeded: int
    failed: int
    skipped: int
    job_ids: list[uuid.UUID]


class JobStatus(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID
    kind: str
    target_id: uuid.UUID
    status: str
    attempts: int
    last_error: str | None
    enqueued_at: datetime
    completed_at: datetime | None


class JobListing(BaseModel):
    pending: int
    jobs: list[JobStatus]


@router.post(
    "/drain",
    response_model=DrainResult,
    dependencies=[Depends(require_internal)],
)
async def drain_synthesis_jobs(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    engagement_id: Annotated[uuid.UUID | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> DrainResult:
    """Pop up to ``limit`` pending jobs for the tenant and run them inline."""
    stmt = (
        select(SynthesisRefreshJob)
        .where(
            SynthesisRefreshJob.tenant_id == tenant_id,
            SynthesisRefreshJob.status == "pending",
        )
        .order_by(SynthesisRefreshJob.enqueued_at.asc())
        .limit(limit)
    )
    if engagement_id is not None:
        stmt = stmt.where(SynthesisRefreshJob.engagement_id == engagement_id)

    jobs = list((await session.execute(stmt)).scalars().all())
    succeeded = 0
    failed = 0
    skipped = 0
    job_ids: list[uuid.UUID] = []
    now = datetime.now(UTC)
    for job in jobs:
        job.status = "running"
        job.started_at = now
        job.attempts = (job.attempts or 0) + 1
        await session.flush()

        try:
            outcome = await _dispatch(session, job, now=now)
        except Exception as exc:  # broad: never let one bad job block the queue
            job.status = "failed"
            job.last_error = str(exc)[:500]
            job.completed_at = datetime.now(UTC)
            await session.commit()
            failed += 1
            job_ids.append(job.id)
            continue

        completion = datetime.now(UTC)
        if outcome is None:
            job.status = "failed"
            job.last_error = "synthesis_unavailable"
            job.completed_at = completion
            skipped += 1
        else:
            job.status = "done"
            job.last_error = None
            job.completed_at = completion
            succeeded += 1
        await session.commit()
        job_ids.append(job.id)

    return DrainResult(
        processed=len(jobs),
        succeeded=succeeded,
        failed=failed,
        skipped=skipped,
        job_ids=job_ids,
    )


@router.get(
    "/jobs",
    response_model=JobListing,
    dependencies=[Depends(require_internal)],
)
async def list_synthesis_jobs(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    engagement_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query(max_length=20)] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> JobListing:
    stmt = select(SynthesisRefreshJob).where(SynthesisRefreshJob.tenant_id == tenant_id)
    if engagement_id is not None:
        stmt = stmt.where(SynthesisRefreshJob.engagement_id == engagement_id)
    if status is not None:
        stmt = stmt.where(SynthesisRefreshJob.status == status)
    rows = list(
        (await session.execute(stmt.order_by(SynthesisRefreshJob.enqueued_at.desc()).limit(limit))).scalars().all()
    )
    pending_q = await session.execute(
        select(SynthesisRefreshJob.id).where(
            SynthesisRefreshJob.tenant_id == tenant_id,
            SynthesisRefreshJob.status == "pending",
        )
    )
    pending_count = len(list(pending_q.scalars().all()))
    return JobListing(
        pending=pending_count,
        jobs=[JobStatus.model_validate(r, from_attributes=True) for r in rows],
    )


async def _dispatch(session: AsyncSession, job: SynthesisRefreshJob, *, now: datetime) -> Any | None:
    if job.kind == "decision_provenance":
        return await refresh_decision_provenance(
            session,
            tenant_id=job.tenant_id,
            engagement_id=job.engagement_id,
            decision_node_id=job.target_id,
            now=now,
            trigger_event_id=job.trigger_event_id,
        )
    if job.kind == "risk_explainer":
        return await refresh_risk_explainer(
            session,
            tenant_id=job.tenant_id,
            engagement_id=job.engagement_id,
            risk_insight_id=job.target_id,
            now=now,
            trigger_event_id=job.trigger_event_id,
        )
    if job.kind == "stakeholder_brief":
        return await refresh_stakeholder_brief(
            session,
            tenant_id=job.tenant_id,
            engagement_id=job.engagement_id,
            stakeholder_node_id=job.target_id,
            now=now,
            trigger_event_id=job.trigger_event_id,
        )
    return None
