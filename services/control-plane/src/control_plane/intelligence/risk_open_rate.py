"""Analyzer: risk_open_rate (design §5.2 #3).

Risks opened minus risks closed in the window. Fires when net-new risks
exceed a tenant-configurable threshold (defaults to 5 per engagement window).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence.base import TemporalInsightWrite

INSIGHT_KIND = "risk_open_rate"
DEFAULT_WINDOW = timedelta(days=14)
_RISK_TYPE = "risk"
_NODE_TYPE_KEY = "node_type"
_DEFAULT_THRESHOLD = 5


def compute(
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    window_start: datetime,
    window_end: datetime,
    opened: list[LedgerEvent],
    closed: list[LedgerEvent],
    threshold: int = _DEFAULT_THRESHOLD,
) -> list[TemporalInsightWrite]:
    opened_count = len(opened)
    closed_count = len(closed)
    net = opened_count - closed_count
    if net <= threshold:
        return []
    severity = _severity_for_net(net, threshold)
    return [
        TemporalInsightWrite(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            insight_kind=INSIGHT_KIND,
            severity=severity,
            title=f"Net risk count rose by {net}",
            narrative=(
                f"{opened_count} risks opened and {closed_count} risks closed in the "
                f"window {window_start.date()}..{window_end.date()}; net +{net} "
                f"exceeds threshold {threshold}."
            ),
            window_start=window_start,
            window_end=window_end,
            evidence_event_ids=[e.id for e in opened],
            metrics={
                "opened": opened_count,
                "closed": closed_count,
                "net": net,
                "threshold": threshold,
            },
        )
    ]


class RiskOpenRateAnalyzer:
    """Fire when net-new risks in the window exceed `threshold`."""

    insight_kind: str = INSIGHT_KIND
    default_window: timedelta = DEFAULT_WINDOW

    def __init__(self, threshold: int = _DEFAULT_THRESHOLD) -> None:
        self._threshold = threshold

    async def run(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID | None,
        window_start: datetime,
        window_end: datetime,
    ) -> list[TemporalInsightWrite]:
        opened = await _fetch(
            session, tenant_id=tenant_id, engagement_id=engagement_id, start=window_start, end=window_end, opened=True
        )
        closed = await _fetch(
            session, tenant_id=tenant_id, engagement_id=engagement_id, start=window_start, end=window_end, opened=False
        )
        return compute(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            window_start=window_start,
            window_end=window_end,
            opened=opened,
            closed=closed,
            threshold=self._threshold,
        )


async def _fetch(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    start: datetime,
    end: datetime,
    opened: bool,
) -> list[LedgerEvent]:
    kind = "insight_opened" if opened else "insight_closed"
    kind_filter = and_(
        LedgerEvent.source_kind == kind,
        LedgerEvent.detail[_NODE_TYPE_KEY].astext == _RISK_TYPE,
    )
    stmt = select(LedgerEvent).where(
        LedgerEvent.tenant_id == tenant_id,
        LedgerEvent.occurred_at >= start,
        LedgerEvent.occurred_at < end,
        kind_filter,
    )
    if engagement_id is not None:
        stmt = stmt.where(LedgerEvent.engagement_id == engagement_id)
    return list((await session.execute(stmt)).scalars().all())


def _severity_for_net(net: int, threshold: int) -> str:
    if net >= threshold * 3:
        return "high"
    if net >= threshold * 2:
        return "medium"
    return "low"


__all__ = [
    "DEFAULT_WINDOW",
    "INSIGHT_KIND",
    "RiskOpenRateAnalyzer",
    "compute",
]
