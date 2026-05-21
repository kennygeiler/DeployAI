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
from control_plane.domain.app_identity.models import AppTenant, AppUser
from control_plane.domain.engagement import Engagement, EngagementMember
from control_plane.phases.machine import DEPLOYMENT_PHASES, default_phase

# Roles a user can hold on an engagement — the cross-functional team.
_ENGAGEMENT_MEMBER_ROLES: tuple[str, ...] = ("fde", "deployment_strategist", "biz_dev")

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


# --- Engagement membership (Phase 2, increment 2.2) ---


class EngagementMemberCreate(BaseModel):
    user_id: uuid.UUID
    role: str


class EngagementMemberRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    engagement_id: uuid.UUID
    user_id: uuid.UUID
    role: str
    created_at: datetime


async def _require_engagement(session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> Engagement:
    r = await session.execute(
        select(Engagement).where(Engagement.tenant_id == tenant_id, Engagement.id == engagement_id)
    )
    eng = r.scalar_one_or_none()
    if eng is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    return eng


@router.get(
    "/{engagement_id}/members",
    response_model=list[EngagementMemberRead],
    dependencies=[Depends(require_internal)],
)
async def list_engagement_members(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[EngagementMember]:
    await _require_engagement(session, tenant_id, engagement_id)
    r = await session.execute(
        select(EngagementMember)
        .where(EngagementMember.engagement_id == engagement_id)
        .order_by(EngagementMember.created_at)
    )
    return list(r.scalars().all())


@router.post(
    "/{engagement_id}/members",
    response_model=EngagementMemberRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def add_engagement_member(
    engagement_id: uuid.UUID,
    body: EngagementMemberCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> EngagementMember:
    await _require_engagement(session, tenant_id, engagement_id)
    if body.role not in _ENGAGEMENT_MEMBER_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid role: {body.role}",
        )
    user = await session.get(AppUser, body.user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found in tenant")
    existing = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.user_id == body.user_id,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="user is already a member of this engagement",
        )
    row = EngagementMember(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        user_id=body.user_id,
        role=body.role,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.delete(
    "/{engagement_id}/members/{member_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def remove_engagement_member(
    engagement_id: uuid.UUID,
    member_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> None:
    await _require_engagement(session, tenant_id, engagement_id)
    r = await session.execute(
        select(EngagementMember).where(
            EngagementMember.engagement_id == engagement_id,
            EngagementMember.id == member_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="member not found")
    await session.delete(row)
    await session.commit()
