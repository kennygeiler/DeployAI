"""Unit tests for the Phase 3 adversarial concern parser (§7.3).

The Haiku-style auditor returns one concern per line (or ``NONE``); the
parser produces structured :class:`AdversarialConcern` objects with a
heuristic severity drawn from keyword needles.
"""

from __future__ import annotations

from control_plane.agents.agent_kenny.nodes.adversarial import (
    classify_severity,
    parse_concerns,
    parse_concerns_structured,
)


def test_parse_concerns_none_response_yields_empty() -> None:
    assert parse_concerns_structured("NONE") == []
    assert parse_concerns_structured("  NONE  ") == []
    assert parse_concerns_structured("") == []


def test_parse_concerns_one_per_line_structured() -> None:
    raw = (
        "- The claim about AD migration is unsupported by the cited events.\n"
        "- Overreach: assumes Kerberos config is fixed.\n"
    )
    out = parse_concerns_structured(raw)
    assert len(out) == 2
    assert out[0].concern_text.startswith("The claim")
    assert out[0].severity == "blocking"
    assert out[1].severity == "warning"


def test_parse_concerns_strips_bullets_and_whitespace() -> None:
    raw = "* first line\n  • second line\n- third line"
    texts = [c.concern_text for c in parse_concerns_structured(raw)]
    assert texts == ["first line", "second line", "third line"]


def test_parse_concerns_drops_stray_none_lines_inside_list() -> None:
    raw = "- real concern about evidence\n- NONE\n- another genuine overreach\n"
    out = parse_concerns_structured(raw)
    assert [c.concern_text for c in out] == [
        "real concern about evidence",
        "another genuine overreach",
    ]


def test_parse_concerns_truncates_at_300_chars() -> None:
    long = "x" * 500
    raw = f"- {long}"
    out = parse_concerns_structured(raw)
    assert len(out) == 1
    assert len(out[0].concern_text) == 300


def test_classify_severity_blocking_keywords() -> None:
    assert classify_severity("This is unsupported by evidence.") == "blocking"
    assert classify_severity("Hallucinated UUID; no evidence found.") == "blocking"
    assert classify_severity("Two cited events contradict each other.") == "blocking"
    assert classify_severity("Citation appears fabricated.") == "blocking"


def test_classify_severity_warning_keywords() -> None:
    assert classify_severity("Slight overreach in the conclusion.") == "warning"
    assert classify_severity("Unstated assumption about timing.") == "warning"
    assert classify_severity("Speculative leap from evidence.") == "warning"
    assert classify_severity("Overgeneralization across stakeholders.") == "warning"


def test_classify_severity_info_default() -> None:
    assert classify_severity("Minor phrasing nit.") == "info"


def test_parse_concerns_legacy_text_view() -> None:
    raw = "- first concern\n- second concern"
    texts = parse_concerns(raw)
    assert texts == ["first concern", "second concern"]


def test_parse_concerns_handles_mixed_severity_in_one_block() -> None:
    raw = (
        "- Claim about W22 approval is unsupported.\n"
        "- Minor phrasing nit on last sentence.\n"
        "- Overconfident about Kerberos timing.\n"
    )
    out = parse_concerns_structured(raw)
    assert [c.severity for c in out] == ["blocking", "info", "warning"]
