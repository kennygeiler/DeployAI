"""Internal API — outbound-MCP kill switch admin route (v2 Phase 5 Wave 3H).

Mounted under ``/internal/v1``. Mirrors the auth + path shape of
``tenant_mcp_configs_internal.py``: requires ``X-DeployAI-Internal-Key``;
the ``{tenant_id}`` segment scopes the row.

Threat-model §5.5 picked **Option B** — a single boolean on
``app_tenants.mcp_outbound_disabled`` that the dispatcher consults first.
Wave 2F shipped the column and the
:func:`set_mcp_outbound_disabled` helper; this route gives the strategist
admin UI (Wave 3H) a writable surface. Every flip emits exactly one
``mcp_outbound_killswitch_changed`` ledger row through the helper —
the route is a thin transport.

The actor identity comes from the standard
``X-DeployAI-Actor-Id`` header the BFF forwards when it has one (JWT
``sub`` or dev override). When the header is absent we fall back to the
literal ``"internal-api"`` so the ledger row always carries a non-empty
``actor_id`` — the helper validates it as a string, not a UUID, per
``mcp_kill_switch_admin.set_mcp_outbound_disabled`` docstring (incident
paths use slugs like ``on-call-sre``).
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.mcp_kill_switch_admin import set_mcp_outbound_disabled
from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant

router = APIRouter(prefix="/tenants", tags=["internal-tenant-mcp-killswitch"])


class KillSwitchRead(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool


class KillSwitchWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    disabled: bool


async def _load_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> AppTenant:
    """Load the ``app_tenants`` row or raise 404.

    The kill switch column lives on this row; if the tenant itself does
    not exist the BFF should surface "tenant not found" rather than
    silently flipping a phantom row.
    """
    stmt = select(AppTenant).where(AppTenant.id == tenant_id)
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="tenant not found",
        )
    return row


@router.get(
    "/{tenant_id}/mcp_killswitch",
    response_model=KillSwitchRead,
    dependencies=[Depends(require_internal)],
)
async def get_mcp_killswitch(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> KillSwitchRead:
    tenant = await _load_tenant(session, tenant_id)
    return KillSwitchRead(disabled=bool(tenant.mcp_outbound_disabled))


@router.post(
    "/{tenant_id}/mcp_killswitch",
    response_model=KillSwitchRead,
    dependencies=[Depends(require_internal)],
)
async def set_mcp_killswitch(
    tenant_id: uuid.UUID,
    body: KillSwitchWrite,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    x_deployai_actor_id: Annotated[str | None, Header(alias="X-DeployAI-Actor-Id")] = None,
) -> KillSwitchRead:
    # 404 before write so the ledger never carries a row for a flip on a
    # non-existent tenant.
    await _load_tenant(session, tenant_id)
    actor_id = (x_deployai_actor_id or "internal-api").strip() or "internal-api"
    await set_mcp_outbound_disabled(
        session,
        tenant_id=tenant_id,
        disabled=body.disabled,
        actor_id=actor_id,
    )
    await session.commit()
    # The helper just issued an UPDATE statement; ``body.disabled`` is now
    # the authoritative on-disk value (commit just made it durable). Echo
    # it back without a second SELECT to keep this route a single round
    # trip on the write path.
    return KillSwitchRead(disabled=body.disabled)


__all__ = ["router"]
