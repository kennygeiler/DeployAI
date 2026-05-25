"""Analyzer: stakeholder_churn (design §5.2 #1).

Counts `member_removed` + `matrix_node_deleted(node_type=stakeholder)` events
in the window vs the prior window of equal length. Fires when current-window
churn > 2x prior; severity scales with rate.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence.base import TemporalInsightWrite

INSIGHT_KIND = "stakeholder_churn"
DEFAULT_WINDOW = timedelta(days=30)
_STAKEHOLDER_DETAIL_KEY = "node_type"
_STAKEHOLDER_TYPE = "stakeholder"


def compute(
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    window_start: datetime,
    window_end: datetime,
    current_events: list[LedgerEvent],
    prior_events: list[LedgerEvent],
) -> list[TemporalInsightWrite]:
    """Pure compute: given pre-fetched events, emit insights (or empty)."""
    current = len(current_events)
    prior = len(prior_events)

    if current < 2:
        return []
    if prior == 0 and current < 3:
        return []
    ratio = current / prior if prior > 0 else float(current)
    if ratio <= 2.0:
        return []

    severity = _severity_for_ratio(ratio)
    evidence = [ev.id for ev in current_events]
    scope = "engagement" if engagement_id else "tenant"
    return [
        TemporalInsightWrite(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            insight_kind=INSIGHT_KIND,
            severity=severity,
            title=f"Stakeholder churn doubled ({prior} → {current})",
            narrative=(
                f"In the {scope} window {window_start.date()}..{window_end.date()}, "
                f"{current} stakeholder-departure events landed vs {prior} in the prior "
                f"window of equal length (ratio {ratio:.2f}x)."
            ),
            window_start=window_start,
            window_end=window_end,
            evidence_event_ids=evidence,
            metrics={
                "current_window_count": current,
                "prior_window_count": prior,
                "ratio": ratio,
            },
        )
    ]


class StakeholderChurnAnalyzer:
    """Fire when stakeholder-leaving rate doubles vs the prior equal window."""

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
        current_events = await _fetch_churn_events(
            session, tenant_id=tenant_id, engagement_id=engagement_id, start=window_start, end=window_end
        )
        prior_events = await _fetch_churn_events(
            session, tenant_id=tenant_id, engagement_id=engagement_id, start=prior_start, end=prior_end
        )
        return compute(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            window_start=window_start,
            window_end=window_end,
            current_events=current_events,
            prior_events=prior_events,
        )


async def _fetch_churn_events(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    start: datetime,
    end: datetime,
) -> list[LedgerEvent]:
    is_member_removed = LedgerEvent.source_kind == "member_removed"
    is_node_deleted = and_(
        LedgerEvent.source_kind == "matrix_node_deleted",
        LedgerEvent.detail[_STAKEHOLDER_DETAIL_KEY].astext == _STAKEHOLDER_TYPE,
    )
    stmt = select(LedgerEvent).where(
        LedgerEvent.tenant_id == tenant_id,
        LedgerEvent.occurred_at >= start,
        LedgerEvent.occurred_at < end,
        or_(is_member_removed, is_node_deleted),
    )
    if engagement_id is not None:
        stmt = stmt.where(LedgerEvent.engagement_id == engagement_id)
    stmt = stmt.order_by(LedgerEvent.occurred_at.asc())
    r = await session.execute(stmt)
    return list(r.scalars().all())


def _severity_for_ratio(ratio: float) -> str:
    if ratio >= 5.0:
        return "high"
    if ratio >= 3.0:
        return "medium"
    return "low"


__all__ = [
    "DEFAULT_WINDOW",
    "INSIGHT_KIND",
    "StakeholderChurnAnalyzer",
    "compute",
]
