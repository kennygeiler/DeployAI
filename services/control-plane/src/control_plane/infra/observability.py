"""Structured logging helpers and Prometheus metrics for ingest paths."""

from __future__ import annotations

import logging

from prometheus_client import REGISTRY, Counter, generate_latest

_LOG = logging.getLogger("deployai.ingest")

_ingest_events = Counter(
    "deployai_ingest_events_written_total",
    "Canonical events written (idempotent insert returned true)",
    ("integration",),
)
_ingest_runs = Counter(
    "deployai_ingest_runs_total",
    "Ingestion run completion",
    ("integration", "status"),
)
_rate_limited = Counter(
    "deployai_rate_limited_total",
    "Requests rejected with 429 by the inbound API rate limiter",
    ("route",),
)


def observe_events_written(integration: str, n: int) -> None:
    if n <= 0:
        return
    _ingest_events.labels(integration).inc(n)


def observe_ingestion_run(integration: str, status: str) -> None:
    _ingest_runs.labels(integration, status).inc()


def observe_rate_limited(route: str) -> None:
    # Label is the route template (or "unknown"), never the raw path —
    # raw paths would explode cardinality on ids and 404 probes.
    _rate_limited.labels(route).inc()


def metrics_payload() -> tuple[bytes, str]:
    return generate_latest(REGISTRY), "text/plain; version=0.0.4; charset=utf-8"


def log_ingest(
    name: str,
    *,
    level: int = logging.INFO,
    **fields: str | int | float | bool | None,
) -> None:
    if not _LOG.isEnabledFor(level):
        return
    parts = " ".join(f"{k}={_fmt(f)}" for k, f in sorted(fields.items()) if f is not None and str(f) != "")
    _LOG.log(level, "ingest event=%s %s", name, parts)


def _fmt(v: str | int | float | bool | None) -> str:
    if isinstance(v, str):
        return v[:500].replace(" ", "_")
    return str(v)
