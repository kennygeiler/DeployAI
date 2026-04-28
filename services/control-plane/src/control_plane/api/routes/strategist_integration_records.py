"""Epic 16 — internal integration registry read (status / reconnect UX)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import AppDbSession
from control_plane.domain.integrations.models import Integration

router = APIRouter(prefix="/strategist", tags=["internal-strategist-integrations"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class IntegrationRecordRead(BaseModel):
    id: str
    provider: str
    display_name: str
    state: str
    disabled_at: datetime | None = None


class IntegrationRecordsRead(BaseModel):
    items: list[IntegrationRecordRead] = Field(default_factory=list)


@router.get(
    "/integration-records",
    response_model=IntegrationRecordsRead,
    dependencies=[Depends(require_internal)],
)
async def list_integration_records(
    session: AppDbSession,
    tenant_id: Annotated[uuid.UUID, Query(description="Tenant scope.")],
) -> IntegrationRecordsRead:
    r = await session.execute(
        select(Integration).where(Integration.tenant_id == tenant_id).order_by(Integration.created_at)
    )
    rows = r.scalars().all()
    items = [
        IntegrationRecordRead(
            id=str(x.id),
            provider=x.provider,
            display_name=x.display_name,
            state=x.state,
            disabled_at=x.disabled_at,
        )
        for x in rows
    ]
    return IntegrationRecordsRead(items=items)
