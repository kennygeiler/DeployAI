"""Unit tests: per-claim citation validator (v2 Phase 0.5, scope-v2 §3.3).

Pure-Python paragraph splitter + regex + UUID-shape check. The DB-existence
verifier is integration-tested in ``test_synthesis_layer.py``; this file
exercises ``validate_per_claim_cites`` and the format-only side of
``verify_citations_exist`` via the regex.
"""

from __future__ import annotations

import uuid

import pytest

from control_plane.agents.synthesis.claim_cite import (
    CITATION_RE,
    Citation,
    validate_per_claim_cites,
)


def test_empty_text_is_flagged_as_missing_cite() -> None:
    report = validate_per_claim_cites("")
    assert not report.ok
    assert report.paragraphs == 0
    assert report.missing_cite_paragraphs == [0]
    assert report.citations == []


def test_paragraph_without_any_cite_is_invalid() -> None:
    text = "This paragraph contains no cite at all, so it is invalid."
    report = validate_per_claim_cites(text)
    assert not report.ok
    assert report.paragraphs == 1
    assert report.missing_cite_paragraphs == [0]
    assert report.citations == []


def test_paragraph_with_event_cite_is_valid() -> None:
    eid = uuid.uuid4()
    text = f"The decision was approved [event:{eid}] in week 22."
    report = validate_per_claim_cites(text)
    assert report.ok
    assert report.paragraphs == 1
    assert report.missing_cite_paragraphs == []
    assert report.citations == [Citation(kind="event", id=eid)]


def test_each_paragraph_must_carry_its_own_cite() -> None:
    eid = uuid.uuid4()
    text = f"First paragraph cites the event [event:{eid}].\n\nSecond paragraph forgets to cite anything at all."
    report = validate_per_claim_cites(text)
    assert not report.ok
    assert report.paragraphs == 2
    assert report.missing_cite_paragraphs == [1]


def test_supports_node_insight_and_turn_kinds() -> None:
    eid = uuid.uuid4()
    nid = uuid.uuid4()
    iid = uuid.uuid4()
    tid = uuid.uuid4()
    text = (
        f"Paragraph one cites an event [event:{eid}] and a node [node:{nid}].\n\n"
        f"Paragraph two cites an insight [insight:{iid}] and a turn [turn:{tid}]."
    )
    report = validate_per_claim_cites(text)
    assert report.ok
    assert {c.kind for c in report.citations} == {"event", "node", "insight", "turn"}
    assert {c.id for c in report.citations} == {eid, nid, iid, tid}


def test_regex_rejects_non_uuid_shape() -> None:
    text = "Broken cite [event:not-a-uuid] should not match."
    assert CITATION_RE.findall(text) == []
    report = validate_per_claim_cites(text)
    assert not report.ok
    assert report.missing_cite_paragraphs == [0]


def test_blank_lines_between_paragraphs_with_extra_whitespace() -> None:
    eid1 = uuid.uuid4()
    eid2 = uuid.uuid4()
    # Multiple blank lines + tab indentation count as a paragraph break.
    text = f"First [event:{eid1}] paragraph.\n\n\n\tSecond [event:{eid2}] paragraph."
    report = validate_per_claim_cites(text)
    assert report.ok
    assert report.paragraphs == 2


def test_multiple_cites_per_paragraph_all_collected() -> None:
    e1, e2 = uuid.uuid4(), uuid.uuid4()
    text = f"Both [event:{e1}] and [event:{e2}] support this single paragraph."
    report = validate_per_claim_cites(text)
    assert report.ok
    assert len(report.citations) == 2
    assert {c.id for c in report.citations} == {e1, e2}


@pytest.mark.parametrize(
    "raw,expected_paragraphs",
    [
        ("one paragraph only", 1),
        ("one\n\ntwo\n\nthree", 3),
        ("   \n\n   ", 0),
    ],
)
def test_paragraph_counting(raw: str, expected_paragraphs: int) -> None:
    report = validate_per_claim_cites(raw)
    assert report.paragraphs == expected_paragraphs
