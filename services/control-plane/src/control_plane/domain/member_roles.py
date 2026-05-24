"""Resolver for engagement-member roles — baked-in union tenant overrides."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.engagement import TenantMemberRole

BUILTIN_MEMBER_ROLES: tuple[str, ...] = ("fde", "deployment_strategist", "biz_dev")


async def list_tenant_member_roles(session: AsyncSession, tenant_id: uuid.UUID) -> list[TenantMemberRole]:
    r = await session.execute(
        select(TenantMemberRole).where(TenantMemberRole.tenant_id == tenant_id).order_by(TenantMemberRole.created_at)
    )
    return list(r.scalars().all())


async def resolve_allowed_member_roles(session: AsyncSession, tenant_id: uuid.UUID) -> set[str]:
    custom = await list_tenant_member_roles(session, tenant_id)
    return set(BUILTIN_MEMBER_ROLES) | {row.name for row in custom}
