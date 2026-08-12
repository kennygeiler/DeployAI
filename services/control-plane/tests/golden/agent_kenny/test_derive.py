"""Unit tests for the derived ground-truth generator (ticket G2).

Pure-function coverage — no Docker, no LLM. The seeded-DB cross-check
(derived strings / citation UUIDs actually exist after a real seed) lives
in ``test_derive_integration.py`` behind the ``integration`` marker.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from control_plane.scenarios.bluestate_xl.events import TOTAL_WEEKS

from .derive import derive_questions, dump_questions_yaml, template_counts
from .runner import _parse_args, load_questions
from .types import Question

# --- Determinism --------------------------------------------------------------


def test_derivation_is_deterministic() -> None:
    a = derive_questions()
    b = derive_questions()
    assert a == b
    # Byte-level too — the YAML artifact must be reproducible.
    assert dump_questions_yaml(a) == dump_questions_yaml(b)


# --- Coverage -----------------------------------------------------------------


def test_at_least_150_questions() -> None:
    assert len(derive_questions()) >= 150


def test_template_coverage_counts() -> None:
    counts = template_counts(derive_questions())
    assert counts == {
        "sponsor_lookup": 40,
        "dependency_lookup": 20,
        "causal_chain": 40,
        "risk_status": 35,
        "temporal": 12,
        "negative_control": 12,
        "cross_engagement": 12,
    }


def test_ids_unique_and_within_length() -> None:
    qs = derive_questions()
    ids = [q.id for q in qs]
    assert len(set(ids)) == len(ids)
    assert all(len(i) <= 64 for i in ids)


def test_every_question_carries_derivation_metadata() -> None:
    for q in derive_questions():
        assert q.template is not None, q.id
        assert q.difficulty is not None, q.id
        assert q.valid_from_week is not None, q.id
        assert 1 <= q.valid_from_week <= TOTAL_WEEKS, q.id


def test_factual_questions_carry_seeded_citation_ids() -> None:
    for q in derive_questions():
        if q.should_idk:
            assert q.expected_citation_ids == [], q.id
        else:
            assert q.expected_citation_ids, q.id
            assert q.expected_answer_contains, q.id


def test_negative_and_cross_engagement_expect_refusal() -> None:
    qs = derive_questions()
    negatives = [q for q in qs if q.template == "negative_control"]
    cross = [q for q in qs if q.template == "cross_engagement"]
    assert all(q.should_idk and q.is_negative_control for q in negatives)
    assert all(q.should_idk and q.category == "cross_engagement" for q in cross)


def test_risk_status_questions_are_monotone() -> None:
    """Open-status questions must target risks that NEVER close; resolved
    ones must be valid only from the close week. That is what makes them
    safe to replay at any longitudinal horizon covering valid_from_week."""
    for q in derive_questions():
        if q.template != "risk_status":
            continue
        assert q.expected_answer_contains[0] in ("open", "resolved"), q.id


def test_limit_truncates() -> None:
    assert len(derive_questions(limit=10)) == 10
    full = derive_questions()
    assert derive_questions(limit=10) == full[:10]


# --- Round trip through the runner's loader -----------------------------------


def test_yaml_round_trip_through_load_questions(tmp_path: Path) -> None:
    qs = derive_questions(limit=25)
    out = tmp_path / "derived.yaml"
    out.write_text(dump_questions_yaml(qs), encoding="utf-8")
    loaded = load_questions(out, enforce_distribution=False)
    assert loaded == qs


def test_alternate_file_skips_distribution_but_rejects_dupes(tmp_path: Path) -> None:
    q = derive_questions(limit=1)[0]
    out = tmp_path / "dupes.yaml"
    out.write_text(dump_questions_yaml([q, q]), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate question ids"):
        load_questions(out, enforce_distribution=False)


def test_curated_default_still_enforces_distribution() -> None:
    qs = load_questions()
    assert len(qs) == 30


def test_curated_questions_default_new_fields() -> None:
    for q in load_questions():
        assert q.expected_citation_ids == []
        assert q.template is None
        assert q.valid_from_week is None


# --- Runner CLI wiring --------------------------------------------------------


def test_parse_args_accepts_questions_path(tmp_path: Path) -> None:
    p = tmp_path / "derived.yaml"
    args = _parse_args(["--questions", str(p)])
    assert args.questions == p
    assert _parse_args([]).questions is None


def test_question_model_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        Question.model_validate(
            {
                "id": "x",
                "category": "direct_lookup",
                "question": "?",
                "expected_min_citations": 0,
                "should_idk": False,
                "bogus_field": 1,
            }
        )
