"""Optional load/duration hook for NFR48 (chunked extraction latency).

Run: ``uv run python -m cartographer.benchmark`` from ``services/cartographer``.

Exits 0; prints human-readable wall time for stub map-reduce over a long synthetic thread.
"""

from __future__ import annotations

import time
import uuid

from cartographer.extract import extract_stub
from cartographer.triage import EventSignals, TriageContext, triage_event


def _synthetic_thread(char_target: int = 250_000) -> str:
    """~250k chars ≈ long thread stress without external files."""
    word = "NYC DOT deployment stakeholder transcript alignment "
    s = word * (char_target // len(word) + 1)
    return s[:char_target]


def run_stub_benchmark(*, char_target: int = 250_000) -> float:
    eid = uuid.uuid4()
    text = _synthetic_thread(char_target)
    event = EventSignals(
        event_id=eid,
        event_keywords=("nyc", "dot", "deployment", "stakeholder", "transcript"),
        text_blob=text,
    )
    ctx = TriageContext(
        phase="P5_scale_execution",
        declared_objectives=("NYC DOT deployment and stakeholder transcript review.",),
        relevance_threshold=0.1,
    )
    t = triage_event(ctx, event, tenant_id="bench")
    t0 = time.perf_counter()
    extract_stub(event, t)
    return time.perf_counter() - t0


def main() -> None:
    sec = run_stub_benchmark()
    print(f"cartographer stub extract wall_seconds={sec:.3f} (NFR48 hook; compare to 300s p95 budget)")


if __name__ == "__main__":
    main()
