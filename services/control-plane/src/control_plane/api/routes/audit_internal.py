"""Internal API — tenant-scoped strategist activity log (Phase C inc 11.2).

Read-only listing over the existing ``strategist_activity_events`` table
(Epic 10 / Story 10.7). Backs the Settings > Audit log UI; sibling
write-paths populate the table.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.strategist_personal import StrategistActivityEvent

router = APIRouter(prefix="/audit-events", tags=["internal-audit"])

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500


class AuditEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    actor_id: uuid.UUID
    category: str
    summary: str
    detail: dict[str, Any]
    ref_id: uuid.UUID | None
    created_at: datetime


@router.get(
    "",
    response_model=list[AuditEventRead],
    dependencies=[Depends(require_internal)],
)
async def list_audit_events(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
    before: Annotated[datetime | None, Query()] = None,
    actor: Annotated[uuid.UUID | None, Query()] = None,
    kind: Annotated[str | None, Query(max_length=200)] = None,
) -> list[StrategistActivityEvent]:
    tenant = await session.get(AppTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    stmt = select(StrategistActivityEvent).where(StrategistActivityEvent.tenant_id == tenant_id)
    if before is not None:
        stmt = stmt.where(StrategistActivityEvent.created_at < before)
    if actor is not None:
        stmt = stmt.where(StrategistActivityEvent.actor_id == actor)
    if kind is not None:
        stmt = stmt.where(StrategistActivityEvent.category == kind)
    stmt = stmt.order_by(StrategistActivityEvent.created_at.desc()).limit(limit)
    r = await session.execute(stmt)
    return list(r.scalars().all())
