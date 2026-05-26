"""Unit tests for AgentState, citation parsing + budget caps (v2 Phase 2)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from control_plane.agents.agent_kenny.budget import AGENT_KENNY_V2_TURN_ESTIMATE
from control_plane.agents.agent_kenny.types import (
    DB_CITATION_KINDS,
    EXTERNAL_CITATION_KINDS,
    MAX_REVISION_ATTEMPTS,
    MAX_TOOL_CALLS_PER_TURN,
    TURN_HARD_TIMEOUT_S,
    AgentState,
    CitationReport,
    ParsedCitation,
    VerifiedCitation,
    filter_db_citations,
    is_uuid_identifier,
    parse_citations,
)

_TENANT = uuid.UUID("00000000-0000-7000-8000-000000000001")
_ENG = uuid.UUID("00000000-0000-7000-8000-000000000002")
_ACTOR = uuid.UUID("00000000-0000-7000-8000-000000000003")


def _state() -> AgentState:
    return AgentState(
        tenant_id=_TENANT,
        engagement_id=_ENG,
        actor_user_id=_ACTOR,
        user_message="hi",
        started_at=datetime(2026, 5, 23, tzinfo=UTC),
    )


def test_budgets_are_constants() -> None:
    assert MAX_TOOL_CALLS_PER_TURN == 8
    assert MAX_REVISION_ATTEMPTS == 2
    assert TURN_HARD_TIMEOUT_S == 60.0
    assert AGENT_KENNY_V2_TURN_ESTIMATE == 4000


def test_state_defaults() -> None:
    s = _state()
    assert s.tool_calls_made == 0
    assert s.revision_attempts == 0
    assert s.adversarial_concerns == []
    assert s.citation_report is None
    assert s.final_text == ""


def test_parse_citations_extracts_all_kinds() -> None:
    text = (
        "Risk noted [event:11111111-1111-4111-8111-111111111111] for node "
        "[node:22222222-2222-4222-8222-222222222222] and insight "
        "[insight:33333333-3333-4333-8333-333333333333]. Slack ref "
        "[slack:msg-abc-123] and a fake [turn:44444444-4444-4444-8444-444444444444]."
    )
    parsed = parse_citations(text)
    kinds = sorted({p.kind for p in parsed})
    assert kinds == ["event", "insight", "node", "slack", "turn"]


def test_parse_citations_dedupes() -> None:
    text = "First [event:11111111-1111-4111-8111-111111111111] then again [event:11111111-1111-4111-8111-111111111111]."
    parsed = parse_citations(text)
    assert len(parsed) == 1


def test_parse_citations_ignores_unknown_prefixes() -> None:
    text = "[banana:abc] is not a known kind"
    assert parse_citations(text) == []


def test_filter_db_citations_excludes_external() -> None:
    parsed = [
        ParsedCitation(kind="event", identifier="11111111-1111-4111-8111-111111111111"),
        ParsedCitation(kind="slack", identifier="msg-abc"),
        ParsedCitation(kind="linear", identifier="LIN-42"),
    ]
    out = filter_db_citations(parsed)
    assert [p.kind for p in out] == ["event"]


def test_is_uuid_identifier_rejects_non_uuid() -> None:
    assert is_uuid_identifier("11111111-1111-4111-8111-111111111111") is True
    assert is_uuid_identifier("msg-abc-123") is False


def test_citation_kind_sets_are_disjoint() -> None:
    assert DB_CITATION_KINDS.isdisjoint(EXTERNAL_CITATION_KINDS)


def test_citation_report_total_sums_all_outcomes() -> None:
    report = CitationReport()
    report.verified.append(VerifiedCitation(kind="event", identifier="a", outcome="verified"))
    report.not_found.append(VerifiedCitation(kind="event", identifier="b", outcome="not_found"))
    report.cross_engagement.append(VerifiedCitation(kind="event", identifier="c", outcome="cross_engagement_leak"))
    report.external.append(VerifiedCitation(kind="slack", identifier="d", outcome="external"))
    assert report.total == 4


def test_state_records_tool_calls_made() -> None:
    s = _state()
    s.tool_calls_made += 1
    assert s.tool_calls_made == 1


def test_state_history_is_independent_per_instance() -> None:
    s1 = _state()
    s2 = _state()
    s1.history.append({"role": "user", "content": "x"})
    assert s2.history == []
