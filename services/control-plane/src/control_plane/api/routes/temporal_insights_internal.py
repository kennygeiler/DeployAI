"""Internal API: temporal insights + analyzer manual-run (Phase F1.c)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.engagement import Engagement
from control_plane.domain.ledger import (
    TEMPORAL_SEVERITIES,
    TEMPORAL_STATUSES,
    TemporalInsight,
)
from control_plane.intelligence.scheduler import analyzers_by_kind, run_analyzers

router = APIRouter(prefix="/temporal-insights", tags=["internal-temporal-insights"])
intelligence_router = APIRouter(prefix="/intelligence", tags=["internal-intelligence"])

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500
_SEVERITY_ORDER: dict[str, int] = {sev: i for i, sev in enumerate(TEMPORAL_SEVERITIES)}


class TemporalInsightRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    insight_kind: str
    severity: str
    title: str
    narrative: str
    window_start: datetime
    window_end: datetime
    evidence_event_ids: list[uuid.UUID]
    metrics: dict[str, Any]
    status: str
    acknowledged_by: uuid.UUID | None
    acknowledged_at: datetime | None
    snoozed_until: datetime | None
    created_at: datetime


class TemporalInsightPatch(BaseModel):
    status: str = Field(min_length=1)
    acknowledged_by: uuid.UUID | None = None
    snooze_days: int | None = Field(default=None, ge=1, le=90)


class IntelligenceRunRequest(BaseModel):
    engagement_id: uuid.UUID | None = None
    analyzer_kinds: list[str] | None = None
    force: bool = False


class IntelligenceRunResponse(BaseModel):
    insights_written: int
    analyzer_kinds_run: list[str]


@router.get(
    "",
    response_model=list[TemporalInsightRead],
    dependencies=[Depends(require_internal)],
)
async def list_temporal_insights(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    engagement_id: Annotated[uuid.UUID | None, Query()] = None,
    status_: Annotated[str | None, Query(alias="status", max_length=32)] = None,
    severity_at_least: Annotated[str | None, Query(max_length=32)] = None,
    kind: Annotated[str | None, Query(max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> list[TemporalInsightRead]:
    if await session.get(AppTenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    stmt = select(TemporalInsight).where(TemporalInsight.tenant_id == tenant_id)
    if engagement_id is not None:
        stmt = stmt.where(TemporalInsight.engagement_id == engagement_id)
    if status_ is not None:
        if status_ not in TEMPORAL_STATUSES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid status: {status_}",
            )
        stmt = stmt.where(TemporalInsight.status == status_)
    else:
        now = datetime.now(UTC)
        stmt = stmt.where(
            or_(
                TemporalInsight.status != "snoozed",
                TemporalInsight.snoozed_until < now,
            )
        )
    if severity_at_least is not None:
        if severity_at_least not in _SEVERITY_ORDER:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"invalid severity: {severity_at_least}",
            )
        floor = _SEVERITY_ORDER[severity_at_least]
        allowed = [sev for sev, idx in _SEVERITY_ORDER.items() if idx >= floor]
        stmt = stmt.where(TemporalInsight.severity.in_(allowed))
    if kind is not None:
        stmt = stmt.where(TemporalInsight.insight_kind == kind)
    stmt = stmt.order_by(TemporalInsight.created_at.desc()).limit(limit)
    rows = (await session.execute(stmt)).scalars().all()
    return [TemporalInsightRead.model_validate(r) for r in rows]


@router.patch(
    "/{insight_id}",
    response_model=TemporalInsightRead,
    dependencies=[Depends(require_internal)],
)
async def patch_temporal_insight(
    insight_id: uuid.UUID,
    body: TemporalInsightPatch,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> TemporalInsightRead:
    if body.status not in TEMPORAL_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid status: {body.status}",
        )
    if body.status == "snoozed" and body.snooze_days is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="snooze_days required when status='snoozed'",
        )
    row = (
        await session.execute(
            select(TemporalInsight).where(
                TemporalInsight.tenant_id == tenant_id,
                TemporalInsight.id == insight_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="insight not found")
    row.status = body.status
    if body.status == "acknowledged":
        row.acknowledged_by = body.acknowledged_by
        if row.acknowledged_at is None:
            row.acknowledged_at = datetime.now(UTC)
    elif body.acknowledged_by is not None:
        row.acknowledged_by = body.acknowledged_by
    if body.status == "snoozed" and body.snooze_days is not None:
        row.snoozed_until = datetime.now(UTC) + timedelta(days=body.snooze_days)
    await session.commit()
    await session.refresh(row)
    return TemporalInsightRead.model_validate(row)


@intelligence_router.post(
    "/run",
    response_model=IntelligenceRunResponse,
    dependencies=[Depends(require_internal)],
)
async def run_intelligence(
    body: IntelligenceRunRequest,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> IntelligenceRunResponse:
    if await session.get(AppTenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    if body.engagement_id is not None:
        eng = (
            await session.execute(
                select(Engagement).where(
                    Engagement.tenant_id == tenant_id,
                    Engagement.id == body.engagement_id,
                )
            )
        ).scalar_one_or_none()
        if eng is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    if body.analyzer_kinds is not None:
        known = analyzers_by_kind()
        unknown = [k for k in body.analyzer_kinds if k not in known]
        if unknown:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"unknown analyzer kinds: {unknown}",
            )
    try:
        writes = await run_analyzers(
            session,
            tenant_id=tenant_id,
            engagement_id=body.engagement_id,
            analyzer_kinds=body.analyzer_kinds,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc
    await session.commit()
    kinds_run = (
        sorted({w.insight_kind for w in writes})
        if writes
        else (body.analyzer_kinds or sorted(analyzers_by_kind().keys()))
    )
    return IntelligenceRunResponse(
        insights_written=len(writes),
        analyzer_kinds_run=list(kinds_run),
    )
