"""Unit tests for the longitudinal replay harness (ticket G3).

Pure-function coverage — no Docker, no LLM. The end-to-end path is
exercised by the weekly ``longitudinal`` job in agent-kenny-eval.yml.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from control_plane.scenarios.bluestate_xl.events import TOTAL_WEEKS

from .derive import derive_questions
from .longitudinal import (
    _parse_args,
    assess_degradation,
    checkpoint_weeks,
    eligible_questions,
    select_subset,
)
from .runner import persist_report
from .types import CategoryDistribution, CheckpointReport, RunReport

# --- Horizon mapping ----------------------------------------------------------


def test_checkpoint_weeks_maps_days_to_whole_weeks() -> None:
    assert checkpoint_weeks(182, TOTAL_WEEKS) == 26
    assert checkpoint_weeks(365, TOTAL_WEEKS) == 52
    assert checkpoint_weeks(730, TOTAL_WEEKS) == 104
    assert checkpoint_weeks(1095, TOTAL_WEEKS) == 156
    assert checkpoint_weeks(1825, TOTAL_WEEKS) == 260


def test_checkpoint_weeks_clamps() -> None:
    assert checkpoint_weeks(7, TOTAL_WEEKS) == 1
    assert checkpoint_weeks(99999, TOTAL_WEEKS) == TOTAL_WEEKS


# --- Eligibility + sampling ---------------------------------------------------


def test_eligible_questions_respects_valid_from_week() -> None:
    qs = derive_questions()
    at_26 = eligible_questions(qs, 26)
    at_260 = eligible_questions(qs, 260)
    assert len(at_26) < len(at_260) == len(qs)
    assert all((q.valid_from_week or 1) <= 26 for q in at_26)
    # Negative + cross-engagement probes are valid from week 1, so even
    # the shortest horizon has refusal coverage.
    assert any(q.template == "negative_control" for q in at_26)
    assert any(q.template == "cross_engagement" for q in at_26)


def test_select_subset_is_deterministic_and_seed_scoped() -> None:
    qs = derive_questions()
    a = select_subset(qs, seed=0, per_checkpoint=12)
    b = select_subset(qs, seed=0, per_checkpoint=12)
    other_seed = select_subset(qs, seed=1, per_checkpoint=12)
    assert a == b
    assert len(a) == 12
    assert [q.id for q in a] != [q.id for q in other_seed]


def test_select_subset_returns_all_when_small() -> None:
    qs = derive_questions(limit=5)
    assert len(select_subset(qs, seed=0, per_checkpoint=12)) == 5


def test_min_horizon_subset_is_valid_at_every_longer_horizon() -> None:
    """The replay's comparability contract: a subset drawn from the
    earliest checkpoint's eligible pool stays valid (monotone facts) at
    every longer horizon."""
    qs = derive_questions()
    min_horizon = checkpoint_weeks(182, TOTAL_WEEKS)
    subset = select_subset(eligible_questions(qs, min_horizon), seed=0, per_checkpoint=12)
    for later in (checkpoint_weeks(730, TOTAL_WEEKS), checkpoint_weeks(1825, TOTAL_WEEKS)):
        later_ids = {q.id for q in eligible_questions(qs, later)}
        assert all(q.id in later_ids for q in subset)


# --- Degradation contract -----------------------------------------------------


def _cp(days: int, pass_rate: float, leaks: int = 0) -> CheckpointReport:
    t0 = datetime(2026, 8, 11, tzinfo=UTC)
    empty_run = RunReport(
        started_at=t0,
        finished_at=t0,
        total_questions=0,
        pass_rate=pass_rate,
        idk_rate=0.0,
        hallucination_rate=0.0,
        cross_engagement_leak_count=leaks,
        latency_p50_ms=0,
        latency_p95_ms=0,
        latency_p99_ms=0,
        by_category=[CategoryDistribution(category="negative", total=0, passes=0, idk=0, leaks=0, pass_rate=0.0)],
        results=[],
    )
    return CheckpointReport(
        checkpoint_days=days,
        horizon_weeks=checkpoint_weeks(days, TOTAL_WEEKS),
        eligible_questions=0,
        questions_run=0,
        question_ids=[],
        pass_rate=pass_rate,
        citation_precision=None,
        latency_p50_ms=0,
        latency_p95_ms=0,
        cross_engagement_leak_count=leaks,
        run=empty_run,
    )


def test_no_degradation_when_flat() -> None:
    degraded, notes = assess_degradation([_cp(182, 0.9), _cp(730, 0.9), _cp(1825, 0.9)], 0.10)
    assert degraded is False
    assert notes == []


def test_drop_within_tolerance_passes() -> None:
    degraded, _ = assess_degradation([_cp(182, 0.90), _cp(1825, 0.81)], 0.10)
    assert degraded is False


def test_drop_beyond_tolerance_fails() -> None:
    degraded, notes = assess_degradation([_cp(182, 0.90), _cp(1825, 0.75)], 0.10)
    assert degraded is True
    assert "1825d" in notes[0]


def test_degradation_compares_against_best_earlier_not_previous() -> None:
    # 0.9 -> 0.85 -> 0.78: the last is compared against 0.9 (best earlier),
    # not 0.85 — a slow bleed across checkpoints still trips the gate.
    degraded, _ = assess_degradation([_cp(182, 0.90), _cp(730, 0.85), _cp(1825, 0.78)], 0.10)
    assert degraded is True


def test_improvement_never_degrades() -> None:
    degraded, _ = assess_degradation([_cp(182, 0.5), _cp(1825, 1.0)], 0.10)
    assert degraded is False


# --- CLI parsing --------------------------------------------------------------


def test_parse_args_defaults() -> None:
    args = _parse_args([])
    assert args.checkpoint_days == [182, 365, 730, 1095, 1825]
    assert args.per_checkpoint == 12
    assert args.tolerance == pytest.approx(0.10)
    assert args.questions == "derived"


def test_parse_args_custom_checkpoints_sorted_deduped() -> None:
    args = _parse_args(["--checkpoints", "730,182,730"])
    assert args.checkpoint_days == [182, 730]


def test_parse_args_tolerance_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEGRADATION_TOLERANCE", "0.25")
    assert _parse_args([]).tolerance == pytest.approx(0.25)
    # Explicit flag wins over the env var.
    assert _parse_args(["--tolerance", "0.05"]).tolerance == pytest.approx(0.05)


def test_parse_args_rejects_bad_values() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--checkpoints", "abc"])
    with pytest.raises(SystemExit):
        _parse_args(["--checkpoints", "3"])
    with pytest.raises(SystemExit):
        _parse_args(["--per-checkpoint", "0"])
    with pytest.raises(SystemExit):
        _parse_args(["--tolerance", "1.5"])


# --- Report persistence (runner --persist-url, ticket G3) ---------------------


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def test_persist_report_posts_with_internal_key(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    seen: dict[str, Any] = {}

    def _fake_post(url: str, **kwargs: Any) -> _FakeResponse:
        seen["url"] = url
        seen["json"] = kwargs.get("json")
        seen["headers"] = kwargs.get("headers")
        return _FakeResponse(201)

    monkeypatch.setattr(httpx, "post", _fake_post)
    ok = persist_report("http://cp/internal/v1/admin/eval-runs", "sekrit", {"pass_rate": 1.0})
    assert ok is True
    assert seen["url"] == "http://cp/internal/v1/admin/eval-runs"
    assert seen["json"] == {"pass_rate": 1.0}
    assert seen["headers"]["X-DeployAI-Internal-Key"] == "sekrit"


def test_persist_report_tolerates_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    import httpx

    def _boom(url: str, **kwargs: Any) -> _FakeResponse:
        raise ConnectionError("endpoint not built yet")

    monkeypatch.setattr(httpx, "post", _boom)
    assert persist_report("http://cp/internal/v1/admin/eval-runs", "k", {}) is False

    monkeypatch.setattr(httpx, "post", lambda url, **kw: _FakeResponse(503))
    assert persist_report("http://cp/internal/v1/admin/eval-runs", "k", {}) is False


def test_runner_parse_args_persist_flags_must_pair() -> None:
    from .runner import _parse_args as runner_parse_args

    with pytest.raises(SystemExit):
        runner_parse_args(["--persist-url", "http://x"])
    args = runner_parse_args(["--persist-url", "http://x", "--persist-key", "k"])
    assert args.persist_url == "http://x"
    assert args.persist_key == "k"
