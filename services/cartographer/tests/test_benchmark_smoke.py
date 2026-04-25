"""NFR48: benchmark entrypoints (small char_target for speed)."""

from __future__ import annotations

from cartographer.benchmark import run_llm_map_reduce_benchmark, run_stub_benchmark


def test_run_stub_benchmark_small() -> None:
    sec = run_stub_benchmark(char_target=500)
    assert sec >= 0.0


def test_run_llm_bench_map_reduce_small() -> None:
    sec = run_llm_map_reduce_benchmark(char_target=400)
    assert sec >= 0.0
