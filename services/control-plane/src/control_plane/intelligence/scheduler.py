"""Analyzer scheduler (design §5.3).

Registers the built-in analyzers and provides a synchronous `run_analyzers`
that invokes them against a given session + window and upserts the resulting
`TemporalInsightWrite` rows. Cron firing is intentionally not wired here —
v1 ships manual-trigger only (`POST /internal/v1/intelligence/run`).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ledger import TemporalInsight
from control_plane.intelligence.base import Analyzer, TemporalInsightWrite
from control_plane.intelligence.decision_cycle_slowdown import DecisionCycleSlowdownAnalyzer
from control_plane.intelligence.engagement_silence import EngagementSilenceAnalyzer
from control_plane.intelligence.risk_open_rate import RiskOpenRateAnalyzer
from control_plane.intelligence.stakeholder_churn import StakeholderChurnAnalyzer


def builtin_analyzers() -> list[Analyzer]:
    return [
        StakeholderChurnAnalyzer(),
        DecisionCycleSlowdownAnalyzer(),
        RiskOpenRateAnalyzer(),
        EngagementSilenceAnalyzer(),
    ]


def analyzers_by_kind(analyzers: Iterable[Analyzer] | None = None) -> dict[str, Analyzer]:
    items = list(analyzers) if analyzers is not None else builtin_analyzers()
    return {a.insight_kind: a for a in items}


async def run_analyzers(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    analyzer_kinds: Sequence[str] | None = None,
    now: datetime | None = None,
    analyzers: Iterable[Analyzer] | None = None,
) -> list[TemporalInsightWrite]:
    """Run the selected analyzers; upsert results; return the writes performed."""
    chosen = _select_analyzers(analyzers_by_kind(analyzers), analyzer_kinds)
    moment = (now or datetime.now(UTC)).astimezone(UTC)
    all_writes: list[TemporalInsightWrite] = []
    for analyzer in chosen:
        window_end = moment
        window_start = moment - analyzer.default_window
        writes = await analyzer.run(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            window_start=window_start,
            window_end=window_end,
        )
        for write in writes:
            await _upsert(session, write)
            all_writes.append(write)
    await session.flush()
    return all_writes


def _select_analyzers(by_kind: dict[str, Analyzer], kinds: Sequence[str] | None) -> list[Analyzer]:
    if kinds is None:
        return list(by_kind.values())
    chosen: list[Analyzer] = []
    for kind in kinds:
        analyzer = by_kind.get(kind)
        if analyzer is None:
            raise ValueError(f"unknown analyzer kind: {kind}")
        chosen.append(analyzer)
    return chosen


async def _upsert(session: AsyncSession, write: TemporalInsightWrite) -> None:
    stmt = (
        pg_insert(TemporalInsight)
        .values(
            id=write.id,
            tenant_id=write.tenant_id,
            engagement_id=write.engagement_id,
            insight_kind=write.insight_kind,
            severity=write.severity,
            title=write.title,
            narrative=write.narrative,
            window_start=write.window_start,
            window_end=write.window_end,
            evidence_event_ids=write.evidence_event_ids,
            metrics=write.metrics,
            status="open",
        )
        .on_conflict_do_update(
            index_elements=["id"],
            set_={
                "severity": write.severity,
                "title": write.title,
                "narrative": write.narrative,
                "evidence_event_ids": write.evidence_event_ids,
                "metrics": write.metrics,
            },
        )
    )
    await session.execute(stmt)


__all__ = [
    "analyzers_by_kind",
    "builtin_analyzers",
    "run_analyzers",
]
