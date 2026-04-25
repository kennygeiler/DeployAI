"""Prometheus metrics for Cartographer (Story 6.1 triage)."""

from __future__ import annotations

from typing import Literal

from prometheus_client import Counter

TriageOutcome = Literal["passed", "triaged_out"]

# Epic text names this `cartographer_triage_rate` — operational rate = irate/ rate() over
# this counter; counter name uses Prometheus _total suffix (OpenMetrics style).
# Label cardinality: avoid unbounded custom phase strings in production; prefer registered phase ids.
CARTOGRAPHER_TRIAGE_OUTCOMES: Counter = Counter(
    "cartographer_triage_outcomes_total",
    "Triage decisions (per tenant + phase + outcome=passed|triaged_out). Triage pass rate: sum(rate by outcome).",
    ("tenant_id", "phase", "outcome"),
)


def observe_triage(
    *,
    tenant_id: str,
    phase: str,
    outcome: TriageOutcome,
) -> None:
    CARTOGRAPHER_TRIAGE_OUTCOMES.labels(
        tenant_id=tenant_id or "unknown",
        phase=phase or "unknown",
        outcome=outcome,
    ).inc()
