"""Internal API: run lint, list flags, resolve flags.

Mounted under ``/internal/v1``. Behind the same ``X-DeployAI-Internal-Key``
header as the other admin routes. Per scope-v2 §4 the nightly safety net
is a Phase 6 dashboard concern; this module supplies the manual /run
endpoint + a paginated read API for the eventual hallucination dashboard.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.lint import LintFlag
from control_plane.workers.wiki_lint import run_lint

router = APIRouter(prefix="/admin/lint", tags=["internal-lint"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


class LintRunResult(BaseModel):
    flag_count: int
    by_kind: dict[str, int]


class LintFlagRead(BaseModel):
    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    kind: str
    target_kind: str
    target_id: uuid.UUID
    detail: dict[str, Any]
    flagged_at: datetime
    resolved_at: datetime | None


class LintFlagListing(BaseModel):
    flags: list[LintFlagRead]
    count: int


@router.post(
    "/run",
    response_model=LintRunResult,
    dependencies=[Depends(require_internal)],
)
async def run_lint_route(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    engagement_id: Annotated[uuid.UUID, Query()],
) -> LintRunResult:
    summary = await run_lint(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        now=datetime.now(UTC),
    )
    await session.commit()
    return LintRunResult(flag_count=summary.flag_count, by_kind=summary.by_kind)


@router.get(
    "/flags",
    response_model=LintFlagListing,
    dependencies=[Depends(require_internal)],
)
async def list_lint_flags(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    engagement_id: Annotated[uuid.UUID | None, Query()] = None,
    kind: Annotated[str | None, Query(max_length=40)] = None,
    resolved: Annotated[bool | None, Query()] = False,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> LintFlagListing:
    stmt = select(LintFlag).where(LintFlag.tenant_id == tenant_id)
    if engagement_id is not None:
        stmt = stmt.where(LintFlag.engagement_id == engagement_id)
    if kind is not None:
        stmt = stmt.where(LintFlag.kind == kind)
    if resolved is False:
        stmt = stmt.where(LintFlag.resolved_at.is_(None))
    elif resolved is True:
        stmt = stmt.where(LintFlag.resolved_at.is_not(None))
    stmt = stmt.order_by(LintFlag.flagged_at.desc()).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return LintFlagListing(
        flags=[
            LintFlagRead(
                id=r.id,
                tenant_id=r.tenant_id,
                engagement_id=r.engagement_id,
                kind=r.kind,
                target_kind=r.target_kind,
                target_id=r.target_id,
                detail=dict(r.detail or {}),
                flagged_at=r.flagged_at,
                resolved_at=r.resolved_at,
            )
            for r in rows
        ],
        count=len(rows),
    )


@router.post(
    "/flags/{flag_id}/resolve",
    response_model=LintFlagRead,
    dependencies=[Depends(require_internal)],
)
async def resolve_lint_flag(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    flag_id: Annotated[uuid.UUID, Path()],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> LintFlagRead:
    row = (
        await session.execute(
            select(LintFlag).where(
                LintFlag.id == flag_id,
                LintFlag.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="lint flag not found")
    if row.resolved_at is None:
        row.resolved_at = datetime.now(UTC)
        await session.flush()
        await session.commit()
    return LintFlagRead(
        id=row.id,
        tenant_id=row.tenant_id,
        engagement_id=row.engagement_id,
        kind=row.kind,
        target_kind=row.target_kind,
        target_id=row.target_id,
        detail=dict(row.detail or {}),
        flagged_at=row.flagged_at,
        resolved_at=row.resolved_at,
    )
