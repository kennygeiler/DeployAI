"""Analyzer: decision_cycle_slowdown (design §5.2 #2).

For decision-node proposal lifecycles, compute `created` → `accepted` time
spans in the current 30d window vs the prior 30d window. Fire when the
mean cycle time has grown by more than 50%.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence.base import TemporalInsightWrite

INSIGHT_KIND = "decision_cycle_slowdown"
DEFAULT_WINDOW = timedelta(days=30)
_NODE_TYPE_KEY = "node_type"
_DECISION_TYPE = "decision"
_PROPOSAL_REF_KEY = "proposal_id"


def _proposal_key(event: LedgerEvent) -> str | None:
    if event.source_ref is not None:
        return str(event.source_ref)
    detail = event.detail or {}
    pid = detail.get(_PROPOSAL_REF_KEY) if isinstance(detail, dict) else None
    return str(pid) if pid is not None else None


def _pair_durations(created: list[LedgerEvent], accepted: list[LedgerEvent]) -> tuple[list[float], list[uuid.UUID]]:
    accepted_by_proposal: dict[str, LedgerEvent] = {}
    for row in accepted:
        pid = _proposal_key(row)
        if pid is not None:
            accepted_by_proposal[pid] = row
    durations: list[float] = []
    evidence: list[uuid.UUID] = []
    for c in created:
        pid = _proposal_key(c)
        if pid is None:
            continue
        a = accepted_by_proposal.get(pid)
        if a is None:
            continue
        delta = (a.occurred_at - c.occurred_at).total_seconds()
        if delta < 0:
            continue
        durations.append(delta)
        evidence.append(a.id)
    return durations, evidence


def compute(
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    window_start: datetime,
    window_end: datetime,
    current_created: list[LedgerEvent],
    current_accepted: list[LedgerEvent],
    prior_created: list[LedgerEvent],
    prior_accepted: list[LedgerEvent],
) -> list[TemporalInsightWrite]:
    current_durations, current_evidence = _pair_durations(current_created, current_accepted)
    prior_durations, _ = _pair_durations(prior_created, prior_accepted)

    if len(current_durations) < 3 or len(prior_durations) < 3:
        return []

    current_mean = sum(current_durations) / len(current_durations)
    prior_mean = sum(prior_durations) / len(prior_durations)
    if prior_mean <= 0:
        return []
    growth = (current_mean - prior_mean) / prior_mean
    if growth <= 0.5:
        return []

    return [
        TemporalInsightWrite(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            insight_kind=INSIGHT_KIND,
            severity=_severity_for_growth(growth),
            title=f"Decision cycle slowed {int(growth * 100)}%",
            narrative=(
                f"Mean decision accept-cycle in the current window grew from "
                f"{prior_mean / 3600:.1f}h to {current_mean / 3600:.1f}h "
                f"(+{int(growth * 100)}%) across {len(current_durations)} decisions."
            ),
            window_start=window_start,
            window_end=window_end,
            evidence_event_ids=current_evidence,
            metrics={
                "current_mean_seconds": current_mean,
                "prior_mean_seconds": prior_mean,
                "current_sample_size": len(current_durations),
                "prior_sample_size": len(prior_durations),
                "growth": growth,
            },
        )
    ]


class DecisionCycleSlowdownAnalyzer:
    """Fire when the mean accept-cycle time for decision proposals rises > 50%."""

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
        window_len = window_end - window_start
        prior_start = window_start - window_len
        prior_end = window_start

        cur_created, cur_accepted = await _fetch_pair(
            session, tenant_id=tenant_id, engagement_id=engagement_id, start=window_start, end=window_end
        )
        pri_created, pri_accepted = await _fetch_pair(
            session, tenant_id=tenant_id, engagement_id=engagement_id, start=prior_start, end=prior_end
        )
        return compute(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            window_start=window_start,
            window_end=window_end,
            current_created=cur_created,
            current_accepted=cur_accepted,
            prior_created=pri_created,
            prior_accepted=pri_accepted,
        )


async def _fetch_pair(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    start: datetime,
    end: datetime,
) -> tuple[list[LedgerEvent], list[LedgerEvent]]:
    base = select(LedgerEvent).where(
        LedgerEvent.tenant_id == tenant_id,
        LedgerEvent.occurred_at >= start,
        LedgerEvent.occurred_at < end,
    )
    if engagement_id is not None:
        base = base.where(LedgerEvent.engagement_id == engagement_id)
    created_stmt = base.where(
        LedgerEvent.source_kind == "llm_proposal_created",
        LedgerEvent.detail[_NODE_TYPE_KEY].astext == _DECISION_TYPE,
    )
    accepted_stmt = base.where(LedgerEvent.source_kind == "proposal_accepted")
    created = list((await session.execute(created_stmt)).scalars().all())
    accepted = list((await session.execute(accepted_stmt)).scalars().all())
    return created, accepted


def _severity_for_growth(growth: float) -> str:
    if growth >= 2.0:
        return "high"
    if growth >= 1.0:
        return "medium"
    return "low"


__all__ = [
    "DEFAULT_WINDOW",
    "INSIGHT_KIND",
    "DecisionCycleSlowdownAnalyzer",
    "compute",
]
