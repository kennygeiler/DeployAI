"""Optional load/duration hook for NFR48 (chunked extraction latency).

Run: ``uv run python -m cartographer.benchmark`` from ``services/cartographer``.

- ``--mode stub`` (default): ``extract_stub`` over a synthetic long thread; wall time
  is local CPU + regex, not a substitute for a live LLM p95 in production.
- ``--mode llm``: same synthetic input through ``extract_map_reduce_llm`` with a
  no-network completer (empty JSON). Measures map-reduce + parse overhead only; not a
  real Anthropic round-trip unless you pass a custom script.

Exits 0; prints human-readable wall time.
"""

from __future__ import annotations

import argparse
import time
import uuid

from cartographer.extract import extract_stub
from cartographer.llm_extract import extract_map_reduce_llm
from cartographer.triage import EventSignals, TriageContext, triage_event


def _synthetic_thread(char_target: int = 250_000) -> str:
    """Long synthetic thread stress without external files."""
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


def run_llm_map_reduce_benchmark(*, char_target: int = 250_000) -> float:
    """``extract_map_reduce_llm`` with a fast in-process completer (no API key, no I/O)."""

    def _empty_completer(_chunk: str) -> str:
        return '{"entities":[]}'

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
    tri = triage_event(ctx, event, tenant_id="bench")
    t0 = time.perf_counter()
    extract_map_reduce_llm(event, tri, completer=_empty_completer)
    return time.perf_counter() - t0


def main() -> None:
    p = argparse.ArgumentParser(description="NFR48 cartographer extraction wall-time hook.")
    p.add_argument(
        "--chars",
        type=int,
        default=250_000,
        metavar="N",
        help="Synthetic thread length in characters (default: 250000).",
    )
    p.add_argument(
        "--mode",
        choices=("stub", "llm"),
        default="stub",
        help="stub=extract_stub; llm=extract_map_reduce_llm with empty-JSON completer (no network).",
    )
    args = p.parse_args()
    if args.mode == "stub":
        sec = run_stub_benchmark(char_target=args.chars)
        print(
            f"cartographer stub extract wall_seconds={sec:.3f} "
            f"(NFR48 hook; char_target={args.chars}; compare to 300s p95 budget where applicable)"
        )
    else:
        sec = run_llm_map_reduce_benchmark(char_target=args.chars)
        print(
            f"cartographer llm path (mock completer) wall_seconds={sec:.3f} "
            f"(char_target={args.chars}; not a live model latency; map-reduce + parse overhead only)"
        )


if __name__ == "__main__":
    main()
