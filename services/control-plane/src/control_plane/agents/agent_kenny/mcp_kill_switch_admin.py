"""Admin write path for the outbound-MCP kill switch (Wave 2F).

Wave 3H's admin UI will eventually POST to a route that calls
:func:`set_mcp_outbound_disabled`. Surfacing the helper here (rather
than only inline in a route) keeps the audit-emit shape testable
without spinning up the FastAPI app, and gives an automation entry
point for incident-response tooling.

Threat-model §5.5 Option B: the flag lives on
``app_tenants.mcp_outbound_disabled``. One row per tenant, one boolean
to flip — see migration ``20260613_0049_mcp_outbound_kill_switch.py``
for the placement rationale.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.app_identity.models import AppTenant
from control_plane.ledger import emit_ledger_event


async def set_mcp_outbound_disabled(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    disabled: bool,
    actor_id: str,
) -> None:
    """Flip the outbound-MCP kill switch for one tenant and emit one ledger row.

    Caller owns the surrounding transaction (mirrors :func:`emit_ledger_event`
    in ``ledger/emitter.py``). Both the ``UPDATE`` and the ledger insert
    flush inside the caller's transaction so a rollback drops both — the
    audit row can never be present for a flip that didn't actually
    happen.

    :param session: Caller-managed AsyncSession. Caller commits.
    :param tenant_id: ``app_tenants.id`` to update.
    :param disabled: New value for ``mcp_outbound_disabled``.
    :param actor_id: String identifier of the human or service flipping
        the switch. Stored in the ledger detail blob, **not** validated as
        a UUID because the on-call incident path may use a service-account
        slug (e.g. ``"on-call-sre"``) rather than an app_user UUID.
    """
    stmt = update(AppTenant).where(AppTenant.id == tenant_id).values(mcp_outbound_disabled=disabled)
    await session.execute(stmt)

    summary = "outbound MCP killswitch ENGAGED" if disabled else "outbound MCP killswitch released"
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=None,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=actor_id,
        source_kind="mcp_outbound_killswitch_changed",
        source_ref=None,
        summary=summary,
        detail={"disabled": disabled, "actor_id": actor_id},
    )


__all__ = ["set_mcp_outbound_disabled"]
