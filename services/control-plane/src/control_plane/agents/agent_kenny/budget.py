"""Per-turn budget for Agent Kenny v2 (scope-v2 §6.2)."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.intelligence.budget import check_and_charge

# Up-front budget reservation per v2 turn. Covers initial LLM call + tool
# roundtrips + adversarial pass. The reserved amount is the worst-case
# pessimistic estimate; over-shoot stays on the tenant's daily ledger.
AGENT_KENNY_V2_TURN_ESTIMATE = 4000


async def charge_turn(session: AsyncSession, *, tenant_id: uuid.UUID) -> bool:
    """Atomically charge the per-turn estimate. Returns ``False`` when exhausted."""
    return await check_and_charge(
        session,
        tenant_id=tenant_id,
        estimate=AGENT_KENNY_V2_TURN_ESTIMATE,
    )


__all__ = ["AGENT_KENNY_V2_TURN_ESTIMATE", "charge_turn"]
