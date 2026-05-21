"""Internal API — engagements (Phase 1, team-tracking pivot).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``; callers
pass ``tenant_id`` as the scope — an engagement belongs to a tenant (the team).
Tenant filtering is enforced in every query (same posture as the strategist
queues internal API). See ``docs/product/deployai-source-of-truth-spec.md``
section 16 (Phase 1).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.engagement import Engagement
from control_plane.phases.machine import DEPLOYMENT_PHASES, default_phase

router = APIRouter(prefix="/engagements", tags=["internal-engagements"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class EngagementCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    customer_account: str | None = Field(default=None, max_length=200)
    current_phase: str = default_phase


class EngagementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    customer_account: str | None
    current_phase: str
    status: str
    created_at: datetime
    updated_at: datetime


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    if await session.get(AppTenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")


@router.get("", response_model=list[EngagementRead], dependencies=[Depends(require_internal)])
async def list_engagements(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[Engagement]:
    await _require_tenant(session, tenant_id)
    r = await session.execute(
        select(Engagement).where(Engagement.tenant_id == tenant_id).order_by(Engagement.created_at.desc())
    )
    return list(r.scalars().all())


@router.post(
    "",
    response_model=EngagementRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_engagement(
    body: EngagementCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> Engagement:
    await _require_tenant(session, tenant_id)
    if body.current_phase not in DEPLOYMENT_PHASES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid phase: {body.current_phase}",
        )
    row = Engagement(
        tenant_id=tenant_id,
        name=body.name,
        customer_account=body.customer_account,
        current_phase=body.current_phase,
        status="active",
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.get("/{engagement_id}", response_model=EngagementRead, dependencies=[Depends(require_internal)])
async def get_engagement(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> Engagement:
    r = await session.execute(
        select(Engagement).where(Engagement.tenant_id == tenant_id, Engagement.id == engagement_id)
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    return row
