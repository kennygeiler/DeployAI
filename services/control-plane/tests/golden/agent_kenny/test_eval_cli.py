"""Unit tests for the eval runner CLI + honest metrics (tickets G1/G4).

Pure-function coverage only — no Docker, no LLM. The end-to-end CLI path
(testcontainer + seed + ASGI transport) is exercised by the PR-gate job
in ci.yml and the scheduled agent-kenny-eval.yml workflow.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from tests.golden.agent_kenny.runner import (
    _aggregate,
    _classify_frames,
    _detect_idk,
    _Frame,
    _parse_args,
    load_questions,
    select_questions,
)
from tests.golden.agent_kenny.types import Question, QuestionResult

# --- Selection (G1) -----------------------------------------------------------


def _questions() -> list[Question]:
    return load_questions()


def test_select_all_by_default() -> None:
    qs = _questions()
    assert select_questions(qs) == qs


def test_select_limit_takes_yaml_order() -> None:
    qs = _questions()
    picked = select_questions(qs, limit=3)
    assert [q.id for q in picked] == [q.id for q in qs[:3]]


def test_select_random_is_seed_deterministic() -> None:
    qs = _questions()
    a = select_questions(qs, limit=5, randomize=True, seed=7)
    b = select_questions(qs, limit=5, randomize=True, seed=7)
    c = select_questions(qs, limit=5, randomize=True, seed=8)
    assert [q.id for q in a] == [q.id for q in b]
    assert len(a) == 5
    # Different seed almost certainly picks a different sample; assert on
    # the concrete seeds used here so the test is not probabilistic.
    assert [q.id for q in a] != [q.id for q in c]


def test_select_question_ids_preserves_request_order() -> None:
    qs = _questions()
    picked = select_questions(qs, question_ids=["q-023", "q-001"])
    assert [q.id for q in picked] == ["q-023", "q-001"]


def test_select_unknown_id_raises() -> None:
    with pytest.raises(ValueError, match="unknown question ids"):
        select_questions(_questions(), question_ids=["q-999"])


def test_parse_args_rejects_ids_with_limit() -> None:
    with pytest.raises(SystemExit):
        _parse_args(["--question-ids", "q-001", "--limit", "3"])


def test_parse_args_default_seed_from_github_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_RUN_ID", "424242")
    assert _parse_args([]).seed == 424242
    monkeypatch.delenv("GITHUB_RUN_ID")
    assert _parse_args([]).seed == 0
    assert _parse_args(["--seed", "7"]).seed == 7


def test_parse_args_runtime_choices() -> None:
    assert _parse_args([]).runtime == "legacy"
    assert _parse_args(["--runtime", "langgraph"]).runtime == "langgraph"
    with pytest.raises(SystemExit):
        _parse_args(["--runtime", "bogus"])


# --- Honest hallucination metric (G4) -----------------------------------------


def _result(
    qid: str = "q-001",
    *,
    category: str = "direct_lookup",
    citations_total: int = 0,
    citations_unverified: int = 0,
    final_text: str = "some factual claim",
    idk: bool = False,
    is_negative_control: bool = False,
) -> QuestionResult:
    return QuestionResult(
        id=qid,
        category=category,
        latency_ms=1,
        tool_calls=0,
        citations_total=citations_total,
        citations_verified=citations_total - citations_unverified,
        citations_unverified=citations_unverified,
        citations_external=0,
        revisions=0,
        adversarial_concerns=0,
        idk=idk,
        final_text=final_text,
        expected_pass=False,
        expected_kind_match=True,
        cross_engagement_leak=False,
        is_negative_control=is_negative_control,
    )


_T0 = datetime(2026, 8, 11, 0, 0, 0, tzinfo=UTC)


def test_zero_citation_factual_answer_scores_fully_unverified() -> None:
    report = _aggregate([_result()], started_at=_T0, finished_at=_T0)
    assert report.hallucination_rate == 1.0


def test_negative_control_decline_is_exempt_from_phantom_penalty() -> None:
    decline = _result(
        "q-017",
        category="negative",
        final_text="I don't know.",
        idk=True,
        is_negative_control=True,
    )
    report = _aggregate([decline], started_at=_T0, finished_at=_T0)
    assert report.hallucination_rate == 0.0

    # Even a NON-idk citation-free reply on a negative control is exempt —
    # the control's pass/fail is judged by expected_pass, not hallucination.
    chatty = _result("q-018", category="negative", final_text="who knows", is_negative_control=True)
    report = _aggregate([chatty], started_at=_T0, finished_at=_T0)
    assert report.hallucination_rate == 0.0


def test_phantom_citations_blend_into_the_denominator() -> None:
    cited = _result("q-002", citations_total=3, citations_unverified=1)
    uncited = _result("q-003")  # zero citations, factual reply
    report = _aggregate([cited, uncited], started_at=_T0, finished_at=_T0)
    # (1 unverified + 1 phantom) / (3 citations + 1 phantom)
    assert report.hallucination_rate == pytest.approx(2 / 4)


def test_empty_reply_is_not_a_phantom_hallucination() -> None:
    empty = _result("q-004", final_text="", idk=True)
    report = _aggregate([empty], started_at=_T0, finished_at=_T0)
    assert report.hallucination_rate == 0.0


# --- Second-tier LLM judge wiring (G4) ----------------------------------------


def _factual_question() -> Question:
    return Question(
        id="q-001",
        category="direct_lookup",
        question="who?",
        expected_answer_contains=["Patricia Vance"],
        expected_min_citations=1,
        expected_kinds=["node"],
        should_idk=False,
    )


def _frames(final_text: str) -> list[_Frame]:
    return [
        _Frame("citation_verified", {"kind": "node", "id": "abc"}),
        _Frame("done", {"final_text": final_text, "revision_attempts": 0}),
    ]


def test_judge_not_invoked_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("EVAL_LLM_JUDGE", raising=False)
    r = _classify_frames(_factual_question(), _frames("Patricia Vance is the sponsor."), latency_ms=1)
    # Substring passes here, so the judge would be skipped regardless.
    assert r.substring_pass is True
    assert r.judged_pass is None

    r = _classify_frames(_factual_question(), _frames("Someone else."), latency_ms=1)
    assert r.substring_pass is False
    assert r.judged_pass is None
    assert r.expected_pass is False


class _FakeJudgeProvider:
    def __init__(self, reply: str, provider_id: str = "judge-fake") -> None:
        self.id = provider_id
        self.reply = reply
        self.calls = 0

    def chat_complete(self, messages, *, temperature=None, max_output_tokens=None):  # type: ignore[no-untyped-def]
        _ = messages, temperature, max_output_tokens
        self.calls += 1
        return self.reply


def test_judge_rescues_semantic_match_on_substring_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    import control_plane.agents.llm as llm_mod

    provider = _FakeJudgeProvider("YES")
    monkeypatch.setenv("EVAL_LLM_JUDGE", "1")
    monkeypatch.setattr(llm_mod, "get_llm_provider", lambda: provider)

    r = _classify_frames(
        _factual_question(),
        _frames("The executive sponsor is P. Vance (Patricia's role since 2023)."),
        latency_ms=1,
    )
    # Substring "Patricia Vance" fails, judge says YES.
    assert r.substring_pass is False
    assert r.judged_pass is True
    assert r.expected_pass is True
    assert provider.calls == 1


def test_judge_no_verdict_keeps_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    import control_plane.agents.llm as llm_mod

    provider = _FakeJudgeProvider("NO")
    monkeypatch.setenv("EVAL_LLM_JUDGE", "1")
    monkeypatch.setattr(llm_mod, "get_llm_provider", lambda: provider)

    r = _classify_frames(_factual_question(), _frames("Someone else entirely."), latency_ms=1)
    assert r.substring_pass is False
    assert r.judged_pass is False
    assert r.expected_pass is False


def test_judge_skipped_silently_on_stub_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    import control_plane.agents.llm as llm_mod

    provider = _FakeJudgeProvider("YES", provider_id="stub")
    monkeypatch.setenv("EVAL_LLM_JUDGE", "1")
    monkeypatch.setattr(llm_mod, "get_llm_provider", lambda: provider)

    r = _classify_frames(_factual_question(), _frames("Someone else entirely."), latency_ms=1)
    assert r.judged_pass is None
    assert r.expected_pass is False
    assert provider.calls == 0


def test_judge_never_runs_for_should_idk_questions(monkeypatch: pytest.MonkeyPatch) -> None:
    import control_plane.agents.llm as llm_mod

    provider = _FakeJudgeProvider("YES")
    monkeypatch.setenv("EVAL_LLM_JUDGE", "1")
    monkeypatch.setattr(llm_mod, "get_llm_provider", lambda: provider)

    q = Question(
        id="q-017",
        category="negative",
        question="x?",
        expected_answer_contains=[],
        expected_min_citations=0,
        expected_kinds=[],
        should_idk=True,
        is_negative_control=True,
    )
    r = _classify_frames(q, [_Frame("done", {"final_text": "an answer", "revision_attempts": 0})], latency_ms=1)
    assert r.judged_pass is None
    assert provider.calls == 0


# --- YAML negative-control flags + stub determinism ---------------------------


def test_exactly_the_six_negative_questions_are_negative_controls() -> None:
    qs = load_questions()
    flagged = {q.id for q in qs if q.is_negative_control}
    negative = {q.id for q in qs if q.category == "negative"}
    assert flagged == negative
    assert len(flagged) == 6


def test_no_response_placeholder_counts_as_idk() -> None:
    # The agent service substitutes "(no response)" for an empty model
    # reply; classifying it as IDK keeps stub-provider runs deterministic
    # for the ci.yml PR gate (negative/cross-engagement subset passes).
    assert _detect_idk("(no response)") is True
    assert _detect_idk("This is (no response) mid-sentence context.") is False
