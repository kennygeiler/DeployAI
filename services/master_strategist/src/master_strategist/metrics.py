"""Prometheus metrics for agent reliability (NFR73 MTBF / failure visibility)."""

from __future__ import annotations

from prometheus_client import Counter

# Cumulative failures per agent + error_code (rate() = failure rate for MTBR reasoning).
AGENT_FAILURES = Counter(
    "agent_failures_total",
    "Count of agent terminal failures (Story 6-8 / NFR73).",
    ("agent", "error_code"),
)


def record_agent_failure(*, agent: str, error_code: str) -> None:
    AGENT_FAILURES.labels(agent=agent, error_code=error_code).inc()
