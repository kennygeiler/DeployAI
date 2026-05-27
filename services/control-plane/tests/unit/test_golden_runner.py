"""Unit tests for the Agent Kenny v2 golden eval harness (Phase 6 Wave A).

Covers the bits we can exercise without a live Postgres + LLM:

- YAML loads and each entry validates as a :class:`Question`.
- Exactly 30 questions, distribution matches scope-v2 §11.1.
- IDs are unique.
- :class:`QuestionResult` + :class:`RunReport` serialise cleanly.
- SSE-frame classification (the pure-function core of ``run_question``)
  produces the expected metrics for a hand-built frame stream.
- IDK detection fires on the documented refusal phrases.
- ``_expected_pass`` honours the category-specific rules.

The integration test (``tests/integration/test_golden_smoke.py``) covers
the live stream-v2 + Postgres path.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from tests.golden.agent_kenny.runner import (
    QUESTIONS_PATH,
    _classify_frames,
    _detect_idk,
    _expected_kind_match,
    _expected_pass,
    _Frame,
    _parse_sse_stream,
    load_questions,
)
from tests.golden.agent_kenny.types import (
    CATEGORIES,
    EXPECTED_DISTRIBUTION,
    CategoryDistribution,
    Question,
    QuestionResult,
    RunReport,
)

# --- YAML loading -------------------------------------------------------------


def test_questions_yaml_exists() -> None:
    assert QUESTIONS_PATH.exists(), QUESTIONS_PATH


def test_load_questions_returns_pydantic_models() -> None:
    questions = load_questions()
    assert all(isinstance(q, Question) for q in questions)


def test_question_count_is_exactly_thirty() -> None:
    questions = load_questions()
    assert len(questions) == 30


def test_category_distribution_matches_spec() -> None:
    questions = load_questions()
    counts: dict[str, int] = dict.fromkeys(EXPECTED_DISTRIBUTION, 0)
    for q in questions:
        counts[q.category] += 1
    assert counts == EXPECTED_DISTRIBUTION


def test_every_category_belongs_to_closed_set() -> None:
    questions = load_questions()
    seen = {q.category for q in questions}
    assert seen.issubset(set(CATEGORIES))


def test_question_ids_unique() -> None:
    questions = load_questions()
    ids = [q.id for q in questions]
    assert len(set(ids)) == len(ids)


def test_question_ids_follow_q_nnn_pattern() -> None:
    questions = load_questions()
    for q in questions:
        assert q.id.startswith("q-"), q.id
        assert q.id[2:].isdigit(), q.id


def test_idk_questions_have_empty_expected_substrings() -> None:
    # ``should_idk=True`` questions cannot also assert that Kenny mentions
    # a specific term — the answer is supposed to be a refusal.
    questions = load_questions()
    for q in questions:
        if q.should_idk:
            assert q.expected_answer_contains == [], q.id
            assert q.expected_min_citations == 0, q.id


def test_positive_questions_have_min_one_citation_expected() -> None:
    questions = load_questions()
    for q in questions:
        if not q.should_idk:
            assert q.expected_min_citations >= 1, q.id


def test_extra_fields_rejected(tmp_path: Path) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        yaml.safe_dump(
            [{**_template_entry(), "id": "q-001", "rogue_field": "nope"}],
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError):
        load_questions(bad)


def test_count_mismatch_raises(tmp_path: Path) -> None:
    bad = tmp_path / "short.yaml"
    bad.write_text(yaml.safe_dump([_template_entry()]), encoding="utf-8")
    with pytest.raises(ValueError, match="expected 30 questions"):
        load_questions(bad)


def test_distribution_mismatch_raises(tmp_path: Path) -> None:
    bad = tmp_path / "skew.yaml"
    entries = []
    for i in range(30):
        e = _template_entry()
        e["id"] = f"q-{i + 1:03d}"
        # Force everything into one category — wrong distribution.
        e["category"] = "direct_lookup"
        entries.append(e)
    bad.write_text(yaml.safe_dump(entries), encoding="utf-8")
    with pytest.raises(ValueError, match="category"):
        load_questions(bad)


def _template_entry() -> dict[str, object]:
    return {
        "id": "q-tmpl",
        "category": "direct_lookup",
        "question": "test?",
        "expected_answer_contains": ["x"],
        "expected_min_citations": 1,
        "expected_kinds": ["node"],
        "should_idk": False,
    }


# --- Model serialisation ------------------------------------------------------


def test_question_serialises_json_round_trip() -> None:
    q = Question(
        id="q-test",
        category="direct_lookup",
        question="who?",
        expected_answer_contains=["a", "b"],
        expected_min_citations=1,
        expected_kinds=["node", "event"],
        should_idk=False,
    )
    payload = q.model_dump_json()
    round = Question.model_validate(json.loads(payload))
    assert round == q


def test_question_result_serialises_with_all_metrics() -> None:
    r = QuestionResult(
        id="q-001",
        category="direct_lookup",
        latency_ms=1234,
        tool_calls=2,
        citations_total=4,
        citations_verified=3,
        citations_unverified=1,
        citations_external=0,
        revisions=0,
        adversarial_concerns=0,
        idk=False,
        final_text="Patricia Vance is the executive sponsor.",
        expected_pass=True,
        expected_kind_match=True,
        cross_engagement_leak=False,
    )
    payload = json.loads(r.model_dump_json())
    assert payload["id"] == "q-001"
    assert payload["latency_ms"] == 1234
    assert payload["citations_total"] == 4
    # Round-trip cleanly.
    assert QuestionResult.model_validate(payload) == r


def test_run_report_serialises_with_results_array() -> None:
    started = datetime(2026, 5, 26, 12, 0, 0, tzinfo=UTC)
    finished = datetime(2026, 5, 26, 12, 5, 0, tzinfo=UTC)
    sample = QuestionResult(
        id="q-001",
        category="direct_lookup",
        latency_ms=100,
        tool_calls=1,
        citations_total=1,
        citations_verified=1,
        citations_unverified=0,
        citations_external=0,
        revisions=0,
        adversarial_concerns=0,
        idk=False,
        final_text="ok",
        expected_pass=True,
        expected_kind_match=True,
        cross_engagement_leak=False,
    )
    report = RunReport(
        started_at=started,
        finished_at=finished,
        total_questions=1,
        pass_rate=1.0,
        idk_rate=0.0,
        hallucination_rate=0.0,
        cross_engagement_leak_count=0,
        latency_p50_ms=100,
        latency_p95_ms=100,
        latency_p99_ms=100,
        by_category=[CategoryDistribution(category="direct_lookup", total=1, passes=1, idk=0, leaks=0, pass_rate=1.0)],
        results=[sample],
    )
    payload = json.loads(report.model_dump_json())
    assert payload["total_questions"] == 1
    assert payload["pass_rate"] == 1.0
    assert len(payload["results"]) == 1
    # Round-trip cleanly.
    assert RunReport.model_validate(payload) == report


# --- SSE parsing + frame classification --------------------------------------


def test_parse_sse_stream_round_trips() -> None:
    payload = (
        'event: tool_call\ndata: {"name":"query_ledger","input":{}}\n\n'
        'event: citation_verified\ndata: {"kind":"event","id":"abc"}\n\n'
        'event: done\ndata: {"final_text":"ok","revision_attempts":0}\n\n'
    )
    frames = _parse_sse_stream(payload)
    events = [f.event for f in frames]
    assert events == ["tool_call", "citation_verified", "done"]


def test_classify_frames_counts_tool_calls_and_citations() -> None:
    q = Question(
        id="q-001",
        category="direct_lookup",
        question="who?",
        expected_answer_contains=["Patricia Vance"],
        expected_min_citations=1,
        expected_kinds=["node"],
        should_idk=False,
    )
    frames = [
        _Frame("tool_call", {"name": "get_matrix_node"}),
        _Frame("tool_call", {"name": "query_ledger"}),
        _Frame("citation_verified", {"kind": "node", "id": "abc"}),
        _Frame("citation_unverified", {"kind": "event", "id": "xyz", "outcome": "not_found"}),
        _Frame("citation_external", {"kind": "slack", "id": "msg-1"}),
        _Frame("adversarial_concern", {"concern_text": "x", "severity": "info"}),
        _Frame("done", {"final_text": "Patricia Vance is the executive sponsor.", "revision_attempts": 1}),
    ]
    r = _classify_frames(q, frames, latency_ms=500)
    assert r.tool_calls == 2
    assert r.citations_verified == 1
    assert r.citations_unverified == 1
    assert r.citations_external == 1
    assert r.citations_total == 3
    assert r.adversarial_concerns == 1
    assert r.revisions == 1
    assert r.final_text.startswith("Patricia Vance")
    assert r.expected_pass is True
    assert r.expected_kind_match is True
    assert r.cross_engagement_leak is False


def test_classify_frames_flags_cross_engagement_leak() -> None:
    q = Question(
        id="q-023",
        category="cross_engagement",
        question="what about other engagement?",
        expected_answer_contains=[],
        expected_min_citations=0,
        expected_kinds=[],
        should_idk=True,
    )
    frames = [
        _Frame("cross_engagement_leak", {"kind": "event", "id": "leak-id"}),
        _Frame("done", {"final_text": "I'm unable to answer that question.", "revision_attempts": 0}),
    ]
    r = _classify_frames(q, frames, latency_ms=10)
    assert r.cross_engagement_leak is True
    # cross_engagement passes either on IDK or on leak detection.
    assert r.expected_pass is True


def test_classify_frames_fails_when_expected_substring_missing() -> None:
    q = Question(
        id="q-001",
        category="direct_lookup",
        question="who?",
        expected_answer_contains=["Patricia Vance"],
        expected_min_citations=1,
        expected_kinds=["node"],
        should_idk=False,
    )
    frames = [
        _Frame("citation_verified", {"kind": "node", "id": "abc"}),
        _Frame("done", {"final_text": "Someone else entirely.", "revision_attempts": 0}),
    ]
    r = _classify_frames(q, frames, latency_ms=10)
    assert r.expected_pass is False


def test_classify_frames_missing_expected_kind_fails_kind_match() -> None:
    q = Question(
        id="q-009",
        category="causal_chain",
        question="trace x",
        expected_answer_contains=["identity"],
        expected_min_citations=2,
        expected_kinds=["event", "node"],
        should_idk=False,
    )
    frames = [
        _Frame("citation_verified", {"kind": "event", "id": "a"}),
        _Frame("done", {"final_text": "The identity decision chain ran from W14.", "revision_attempts": 0}),
    ]
    r = _classify_frames(q, frames, latency_ms=10)
    # "node" kind expected but never seen — should fail.
    assert r.expected_kind_match is False


# --- IDK detection ------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "I don't know.",
        "I do not know.",
        "I can't answer that question.",
        "Unable to find that information.",
        "No relevant data in the ledger.",
        "I'm unable to answer that question.",
        "No information about that.",
        "Insufficient evidence to answer.",
        "",
    ],
)
def test_detect_idk_fires_on_refusal_phrases(text: str) -> None:
    assert _detect_idk(text) is True


def test_detect_idk_does_not_fire_on_a_real_answer() -> None:
    assert _detect_idk("Patricia Vance is the executive sponsor.") is False


def test_expected_pass_negative_requires_idk_and_no_leak() -> None:
    q = Question(
        id="q-017",
        category="negative",
        question="x?",
        expected_answer_contains=[],
        expected_min_citations=0,
        expected_kinds=[],
        should_idk=True,
    )
    assert _expected_pass(q, final_text="I don't know.", idk=True, leak=False) is True
    assert _expected_pass(q, final_text="some answer", idk=False, leak=False) is False


def test_expected_pass_positive_requires_all_substrings() -> None:
    q = Question(
        id="q-001",
        category="direct_lookup",
        question="x?",
        expected_answer_contains=["Patricia", "Vance"],
        expected_min_citations=1,
        expected_kinds=["node"],
        should_idk=False,
    )
    assert _expected_pass(q, final_text="patricia vance is the sponsor", idk=False, leak=False) is True
    assert _expected_pass(q, final_text="just patricia mentioned", idk=False, leak=False) is False
    # Even if every substring matches, an IDK marker fails the answer.
    assert (
        _expected_pass(q, final_text="Patricia Vance — but I don't know if she's the sponsor.", idk=True, leak=False)
        is False
    )


def test_expected_kind_match_trivial_when_no_kinds_expected() -> None:
    q = Question(
        id="q-017",
        category="negative",
        question="x?",
        expected_answer_contains=[],
        expected_min_citations=0,
        expected_kinds=[],
        should_idk=True,
    )
    assert _expected_kind_match(q, set()) is True
    assert _expected_kind_match(q, {"event"}) is True
