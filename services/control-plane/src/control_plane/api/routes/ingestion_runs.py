"""Internal ingestion run listing (Epic 3 Story 3-8) for ``/admin/runs``."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import get_app_db_session
from control_plane.domain.ingest_runs import IngestionRun

router = APIRouter(prefix="/ingestion-runs", tags=["internal-ingestion-runs"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class IngestionRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    integration: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    events_written: int
    error_count: int
    error_summary: dict[str, Any]
    meta: dict[str, Any]


@router.get(
    "",
    response_model=list[IngestionRunRead],
    dependencies=[Depends(require_internal)],
)
async def list_ingestion_runs(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    limit: int = Query(100, le=500, ge=1),
) -> list[IngestionRunRead]:
    r = await session.execute(
        select(IngestionRun).order_by(desc(IngestionRun.started_at)).limit(int(limit))
    )
    rows = r.scalars().all()
    return [IngestionRunRead.model_validate(x) for x in rows]
