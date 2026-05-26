"""``retrieve_initial_context`` — first node in the graph (scope-v2 §6.1).

Pulls a small dense seed context (matrix summary, open risks, recent
ledger) so the LLM has a fighting chance of resolving the user's
question without burning tool calls on warm-up reconnaissance.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.types import AgentState
from control_plane.agents.tools.analysis import (
    get_engagement_summary,
    get_open_risks,
)
from control_plane.agents.tools.ledger import query_ledger

_RECENT_LEDGER_DAYS = 30
_RECENT_LEDGER_LIMIT = 30
_OPEN_RISKS_LIMIT = 15


async def retrieve_initial_context(session: AsyncSession, state: AgentState) -> AgentState:
    """Populate ``state.initial_context`` with the three seed bundles."""
    summary = await get_engagement_summary(
        session,
        tenant_id=state.tenant_id,
        engagement_id=state.engagement_id,
        emit_audit=False,
    )
    risks = await get_open_risks(
        session,
        tenant_id=state.tenant_id,
        engagement_id=state.engagement_id,
        limit=_OPEN_RISKS_LIMIT,
        emit_audit=False,
    )
    cutoff = state.started_at - timedelta(days=_RECENT_LEDGER_DAYS)
    recent = await query_ledger(
        session,
        tenant_id=state.tenant_id,
        engagement_id=state.engagement_id,
        from_=cutoff,
        limit=_RECENT_LEDGER_LIMIT,
        emit_audit=False,
    )
    initial: dict[str, Any] = {
        "summary": summary.rows[0] if summary.rows else {},
        "open_risks": risks.rows,
        "recent_ledger": recent.rows,
    }
    state.initial_context = initial
    return state


__all__ = ["retrieve_initial_context"]
