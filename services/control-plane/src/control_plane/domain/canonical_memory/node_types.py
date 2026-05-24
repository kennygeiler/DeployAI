"""Tenant-scoped custom matrix node-type registry helpers (Sprint 6 inc 1).

The 7 baked-in node types live in ``matrix.py`` as ``MATRIX_NODE_TYPES``;
this module exposes the union of those plus any tenant-registered
``tenant_node_types`` rows so the matrix-CRUD validator and the
Cartographer prompt context can resolve the full allowed set per tenant.
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.canonical_memory.matrix import MATRIX_NODE_TYPES, TenantNodeType

BUILTIN_NODE_TYPES: tuple[str, ...] = MATRIX_NODE_TYPES


async def list_tenant_node_types(session: AsyncSession, tenant_id: uuid.UUID) -> list[TenantNodeType]:
    """Return the tenant's custom node-type rows ordered by name."""
    r = await session.execute(
        select(TenantNodeType).where(TenantNodeType.tenant_id == tenant_id).order_by(TenantNodeType.name)
    )
    return list(r.scalars().all())


async def resolve_allowed_node_types(session: AsyncSession, tenant_id: uuid.UUID) -> set[str]:
    """Union of baked-in node types + this tenant's custom names."""
    custom = await list_tenant_node_types(session, tenant_id)
    return set(BUILTIN_NODE_TYPES) | {row.name for row in custom}
