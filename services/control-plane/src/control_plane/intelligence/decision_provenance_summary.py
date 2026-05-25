"""Analyzer: decision_provenance_summary (design §5.2 #9, Phase F2.b).

LLM-assisted. For each ``proposal_accepted`` event in the last 24h that
landed a decision-type matrix node, walks the upstream causal chain via
``ledger_event_causes`` (bounded depth) and asks the tenant-resolved LLM
for a 2-sentence narrative answering "why does this decision exist".
Stored in ``temporal_insights.detail.narrative`` (analyzer-output column).

Gated by the per-tenant daily LLM token budget — when the budget is
exhausted, the analyzer skips the LLM call and returns no insight for
that proposal rather than raising.
"""

from __future__ import annotations

import logging
import uuid
from collections import deque
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.llm import get_llm_provider, resolve_tenant_llm_provider
from control_plane.domain.ledger import LedgerEvent, LedgerEventCause
from control_plane.intelligence.base import TemporalInsightWrite
from control_plane.intelligence.budget import check_and_charge

INSIGHT_KIND = "decision_provenance_summary"
DEFAULT_WINDOW = timedelta(hours=24)
_MAX_CHAIN_DEPTH = 5
_MAX_CHAIN_NODES = 25
_LLM_TOKEN_ESTIMATE = 800
_LLM_MAX_OUTPUT_TOKENS = 200
_LLM_TEMPERATURE = 0.2
_NODE_TYPE_KEY = "node_type"
_DECISION_TYPE = "decision"

_log = logging.getLogger(__name__)


class DecisionProvenanceSummaryAnalyzer:
    """Generate a 2-sentence "why does this decision exist" narrative per accepted decision."""

    insight_kind: str = INSIGHT_KIND
    default_window: timedelta = DEFAULT_WINDOW

    async def run(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> list[TemporalInsightWrite]:
        accepted = await _fetch_accepted_decisions(
            session, tenant_id=tenant_id, engagement_id=engagement_id, start=window_start, end=window_end
        )
        if not accepted:
            return []

        env_fallback = get_llm_provider()
        provider = await resolve_tenant_llm_provider(session, tenant_id, env_fallback)

        writes: list[TemporalInsightWrite] = []
        for event in accepted:
            chain = await _walk_chain(session, event_id=event.id, tenant_id=tenant_id)
            if not chain:
                continue
            granted = await check_and_charge(session, tenant_id=tenant_id, estimate=_LLM_TOKEN_ESTIMATE)
            if not granted:
                _log.info(
                    "decision_provenance_summary: budget exhausted for tenant %s; skipping remaining",
                    tenant_id,
                )
                break
            narrative = _ask_llm(provider, chain=chain, anchor=event)
            if narrative is None:
                continue
            writes.append(
                TemporalInsightWrite(
                    tenant_id=tenant_id,
                    engagement_id=event.engagement_id,
                    insight_kind=INSIGHT_KIND,
                    severity="info",
                    title=f"Provenance: {event.summary[:120]}",
                    narrative=f"AI-generated draft: {narrative}",
                    window_start=window_start,
                    window_end=window_end,
                    evidence_event_ids=[event.id, *[c.id for c in chain]],
                    metrics={
                        "chain_depth": len(chain),
                        "anchor_event_id": str(event.id),
                        "ai_generated": True,
                    },
                )
            )
        return writes


async def _fetch_accepted_decisions(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    start: datetime,
    end: datetime,
) -> list[LedgerEvent]:
    stmt = (
        select(LedgerEvent)
        .where(
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.source_kind == "proposal_accepted",
            LedgerEvent.occurred_at >= start,
            LedgerEvent.occurred_at < end,
            LedgerEvent.detail[_NODE_TYPE_KEY].astext == _DECISION_TYPE,
        )
        .order_by(LedgerEvent.occurred_at.asc())
    )
    if engagement_id is not None:
        stmt = stmt.where(LedgerEvent.engagement_id == engagement_id)
    return list((await session.execute(stmt)).scalars().all())


async def _walk_chain(session: AsyncSession, *, event_id: uuid.UUID, tenant_id: uuid.UUID) -> list[LedgerEvent]:
    visited: set[uuid.UUID] = {event_id}
    frontier: deque[tuple[uuid.UUID, int]] = deque([(event_id, 0)])
    collected: list[LedgerEvent] = []
    while frontier and len(collected) < _MAX_CHAIN_NODES:
        current_id, depth = frontier.popleft()
        if depth >= _MAX_CHAIN_DEPTH:
            continue
        parent_ids = list(
            (
                await session.execute(
                    select(LedgerEventCause.caused_by_id).where(LedgerEventCause.event_id == current_id)
                )
            )
            .scalars()
            .all()
        )
        if not parent_ids:
            continue
        parents = list(
            (
                await session.execute(
                    select(LedgerEvent).where(
                        LedgerEvent.id.in_(parent_ids),
                        LedgerEvent.tenant_id == tenant_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for parent in parents:
            if parent.id in visited:
                continue
            visited.add(parent.id)
            collected.append(parent)
            frontier.append((parent.id, depth + 1))
            if len(collected) >= _MAX_CHAIN_NODES:
                break
    return collected


def _ask_llm(provider: Any, *, chain: list[LedgerEvent], anchor: LedgerEvent) -> str | None:
    bullets = "\n".join(f"- {e.occurred_at.isoformat()} | {e.source_kind} | {e.summary[:200]}" for e in chain)
    messages = [
        {
            "role": "system",
            "content": (
                "You summarize causal histories of business decisions. "
                "Reply with exactly two sentences explaining why the decision exists, "
                "grounded only in the provided events. No preamble."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Decision event: {anchor.occurred_at.isoformat()} | {anchor.source_kind} | "
                f"{anchor.summary[:300]}\n\nUpstream causal chain (most-recent first):\n{bullets}"
            ),
        },
    ]
    try:
        raw = provider.chat_complete(
            messages,
            temperature=_LLM_TEMPERATURE,
            max_output_tokens=_LLM_MAX_OUTPUT_TOKENS,
        )
    except Exception as e:  # broad: best-effort, never fail analyzer run
        _log.warning("decision_provenance_summary: LLM call failed: %s", e)
        return None
    text = (raw or "").strip()
    return text or None


__all__ = [
    "DEFAULT_WINDOW",
    "INSIGHT_KIND",
    "DecisionProvenanceSummaryAnalyzer",
]
