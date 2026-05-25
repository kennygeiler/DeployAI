"""Analyzer: extractor_acceptance_drift (design §5.2 #5, Phase F2.b).

Statistical only — no LLM. Compares the rolling acceptance rate of LLM
matrix-extractor proposals in the trailing 14d window against the
trailing 30d baseline. Fires when the rate has dropped by more than 25
percentage points: a likely signal of extractor prompt regression or
transcript-format change.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ledger import LedgerEvent
from control_plane.intelligence.base import TemporalInsightWrite

INSIGHT_KIND = "extractor_acceptance_drift"
DEFAULT_WINDOW = timedelta(days=14)
_BASELINE_WINDOW = timedelta(days=30)
_DRIFT_THRESHOLD_PP = 0.25
_MIN_PROPOSALS = 5
_EXTRACTOR_ACTOR = "agent:matrix_extractor"
_PROPOSAL_REF_KEY = "proposal_id"


def _proposal_key(event: LedgerEvent) -> str | None:
    if event.source_ref is not None:
        return str(event.source_ref)
    detail = event.detail or {}
    pid = detail.get(_PROPOSAL_REF_KEY) if isinstance(detail, dict) else None
    return str(pid) if pid is not None else None


def _acceptance_rate(
    created: list[LedgerEvent],
    accepted: list[LedgerEvent],
) -> tuple[float, int]:
    proposal_ids = {pid for c in created if (pid := _proposal_key(c)) is not None}
    if not proposal_ids:
        return 0.0, 0
    accepted_ids = {pid for a in accepted if (pid := _proposal_key(a)) is not None and pid in proposal_ids}
    return len(accepted_ids) / len(proposal_ids), len(proposal_ids)


def compute(
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    window_start: datetime,
    window_end: datetime,
    window_created: list[LedgerEvent],
    window_accepted: list[LedgerEvent],
    baseline_created: list[LedgerEvent],
    baseline_accepted: list[LedgerEvent],
) -> list[TemporalInsightWrite]:
    window_rate, window_n = _acceptance_rate(window_created, window_accepted)
    if window_n < _MIN_PROPOSALS:
        return []
    baseline_rate, baseline_n = _acceptance_rate(baseline_created, baseline_accepted)
    if baseline_n < _MIN_PROPOSALS:
        return []
    drop = baseline_rate - window_rate
    if drop <= _DRIFT_THRESHOLD_PP:
        return []
    evidence = [c.id for c in window_created]
    return [
        TemporalInsightWrite(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            insight_kind=INSIGHT_KIND,
            severity=_severity_for_drop(drop),
            title=f"Extractor acceptance dropped {int(drop * 100)}pp",
            narrative=(
                f"LLM matrix-extractor acceptance fell from {int(baseline_rate * 100)}% "
                f"(trailing 30d, {baseline_n} proposals) to {int(window_rate * 100)}% "
                f"(trailing 14d, {window_n} proposals) — a {int(drop * 100)}pp drop."
            ),
            window_start=window_start,
            window_end=window_end,
            evidence_event_ids=evidence,
            metrics={
                "window_acceptance_rate": window_rate,
                "baseline_acceptance_rate": baseline_rate,
                "window_proposal_count": window_n,
                "baseline_proposal_count": baseline_n,
                "drop_pp": drop,
            },
        )
    ]


class ExtractorAcceptanceDriftAnalyzer:
    """Fire when extractor acceptance rate drops > 25pp vs the 30d baseline."""

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
        baseline_start = window_end - _BASELINE_WINDOW
        window_created, window_accepted = await _fetch_pair(
            session, tenant_id=tenant_id, engagement_id=engagement_id, start=window_start, end=window_end
        )
        baseline_created, baseline_accepted = await _fetch_pair(
            session, tenant_id=tenant_id, engagement_id=engagement_id, start=baseline_start, end=window_end
        )
        return compute(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            window_start=window_start,
            window_end=window_end,
            window_created=window_created,
            window_accepted=window_accepted,
            baseline_created=baseline_created,
            baseline_accepted=baseline_accepted,
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
        LedgerEvent.actor_kind == _EXTRACTOR_ACTOR,
    )
    accepted_stmt = base.where(LedgerEvent.source_kind == "proposal_accepted")
    created = list((await session.execute(created_stmt)).scalars().all())
    accepted = list((await session.execute(accepted_stmt)).scalars().all())
    return created, accepted


def _severity_for_drop(drop: float) -> str:
    if drop >= 0.5:
        return "high"
    if drop >= 0.35:
        return "medium"
    return "low"


__all__ = [
    "DEFAULT_WINDOW",
    "INSIGHT_KIND",
    "ExtractorAcceptanceDriftAnalyzer",
    "compute",
]
