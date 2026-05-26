"""Unit tests for the Phase 2 graph routers (no LLM, no DB)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from control_plane.agents.agent_kenny.graph import (
    NODE_ADVERSARIAL,
    NODE_DISPATCH_TOOLS,
    NODE_EXTRACT_CITATIONS,
    NODE_PERSIST,
    NODE_REVISE,
    build_graph,
    has_tool_calls_router,
    unverified_router,
)
from control_plane.agents.agent_kenny.nodes.llm_call import (
    parse_thinking,
    parse_tool_calls,
    strip_protocol_blocks,
)
from control_plane.agents.agent_kenny.nodes.tool_dispatch import (
    has_pending_tool_calls,
    tool_budget_remaining,
    validate_input,
)
from control_plane.agents.agent_kenny.types import (
    MAX_REVISION_ATTEMPTS,
    MAX_TOOL_CALLS_PER_TURN,
    AgentState,
    CitationReport,
    VerifiedCitation,
)
from control_plane.agents.tools import ToolError


def _state() -> AgentState:
    return AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="hi",
        started_at=datetime(2026, 5, 23, tzinfo=UTC),
    )


def test_has_tool_calls_router_routes_to_dispatch_when_pending() -> None:
    s = _state()
    s.pending_tool_calls = [{"name": "query_ledger", "input": {}}]
    assert has_tool_calls_router(s) == NODE_DISPATCH_TOOLS


def test_has_tool_calls_router_routes_to_extract_when_idle() -> None:
    assert has_tool_calls_router(_state()) == NODE_EXTRACT_CITATIONS


def test_has_tool_calls_router_caps_at_max_tools() -> None:
    s = _state()
    s.pending_tool_calls = [{"name": "query_ledger", "input": {}}]
    s.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    assert has_tool_calls_router(s) == NODE_EXTRACT_CITATIONS


def test_unverified_router_persists_on_cross_engagement_leak() -> None:
    s = _state()
    report = CitationReport()
    report.cross_engagement.append(VerifiedCitation(kind="event", identifier="x", outcome="cross_engagement_leak"))
    s.citation_report = report
    assert unverified_router(s) == NODE_PERSIST


def test_unverified_router_revises_when_not_found_under_cap() -> None:
    s = _state()
    report = CitationReport()
    report.not_found.append(VerifiedCitation(kind="event", identifier="y", outcome="not_found"))
    s.citation_report = report
    s.revision_attempts = 0
    assert unverified_router(s) == NODE_REVISE


def test_unverified_router_stops_revising_at_cap() -> None:
    s = _state()
    report = CitationReport()
    report.not_found.append(VerifiedCitation(kind="event", identifier="y", outcome="not_found"))
    s.citation_report = report
    s.revision_attempts = MAX_REVISION_ATTEMPTS
    assert unverified_router(s) == NODE_ADVERSARIAL


def test_unverified_router_routes_to_adversarial_when_clean() -> None:
    s = _state()
    s.citation_report = CitationReport()
    assert unverified_router(s) == NODE_ADVERSARIAL


def test_build_graph_returns_compiled_state_graph() -> None:
    g = build_graph()
    assert g is not None
    # Should have a `.invoke` and `.astream` interface (compiled).
    assert hasattr(g, "invoke")


def test_parse_tool_calls_extracts_json_blocks() -> None:
    text = '<thinking>need to look</thinking><tool_call>{"name": "query_ledger", "input": {"limit": 5}}</tool_call>'
    calls = parse_tool_calls(text)
    assert calls == [{"name": "query_ledger", "input": {"limit": 5}}]


def test_parse_tool_calls_skips_malformed() -> None:
    text = '<tool_call>not json</tool_call><tool_call>{"name": "q"}</tool_call>'
    calls = parse_tool_calls(text)
    assert calls == [{"name": "q", "input": {}}]


def test_parse_thinking_extracts_text() -> None:
    text = "<thinking>step one</thinking>reply<thinking>step two</thinking>"
    assert parse_thinking(text) == ["step one", "step two"]


def test_strip_protocol_blocks_returns_user_visible_text() -> None:
    text = "before<tool_call>{}</tool_call><thinking>x</thinking>after"
    assert strip_protocol_blocks(text) == "beforeafter"


def test_has_pending_tool_calls_helper() -> None:
    s = _state()
    assert has_pending_tool_calls(s) is False
    s.pending_tool_calls = [{"name": "x", "input": {}}]
    assert has_pending_tool_calls(s) is True


def test_tool_budget_remaining_helper() -> None:
    s = _state()
    assert tool_budget_remaining(s) == MAX_TOOL_CALLS_PER_TURN
    s.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    assert tool_budget_remaining(s) == 0
    s.tool_calls_made = MAX_TOOL_CALLS_PER_TURN + 5
    assert tool_budget_remaining(s) == 0


def test_validate_input_accepts_complete_payload() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    validate_input(schema, {"a": "ok"})


def test_validate_input_rejects_missing_required() -> None:
    schema = {"type": "object", "properties": {"a": {"type": "string"}}, "required": ["a"]}
    with pytest.raises(ToolError):
        validate_input(schema, {})


def test_validate_input_passes_through_non_object() -> None:
    validate_input({"type": "array"}, {})  # no-op; should not raise
