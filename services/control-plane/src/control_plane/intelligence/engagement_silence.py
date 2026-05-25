"""Analyzer: engagement_silence (design §5.2 #4).

Fire info-level when no ledger events landed on an engagement in the last
14 days (i.e. the entire window). Skips tenant-wide runs (engagement_id=None)
since "tenant has been silent" is rarely actionable on its own.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence.base import TemporalInsightWrite

INSIGHT_KIND = "engagement_silence"
DEFAULT_WINDOW = timedelta(days=14)


def compute(
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    window_start: datetime,
    window_end: datetime,
    event_count: int,
) -> list[TemporalInsightWrite]:
    if engagement_id is None:
        return []
    if event_count > 0:
        return []
    days = (window_end - window_start).days
    return [
        TemporalInsightWrite(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            insight_kind=INSIGHT_KIND,
            severity="info",
            title=f"No activity in {days} days",
            narrative=(
                f"This engagement has had zero ledger events in the {days}-day window ending {window_end.date()}."
            ),
            window_start=window_start,
            window_end=window_end,
            evidence_event_ids=[],
            metrics={"event_count": 0, "window_days": days},
        )
    ]


class EngagementSilenceAnalyzer:
    """Info-level fire when an engagement has zero events in the window."""

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
        if engagement_id is None:
            return []
        stmt = select(func.count(LedgerEvent.id)).where(
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.engagement_id == engagement_id,
            LedgerEvent.occurred_at >= window_start,
            LedgerEvent.occurred_at < window_end,
        )
        count = int((await session.execute(stmt)).scalar_one())
        return compute(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            window_start=window_start,
            window_end=window_end,
            event_count=count,
        )


__all__ = [
    "DEFAULT_WINDOW",
    "INSIGHT_KIND",
    "EngagementSilenceAnalyzer",
    "compute",
]
