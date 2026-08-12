"""Unit tests for the zero-citation revision trigger (production GAP 1).

A factual reply with NO ``[kind:UUID]`` markers after successful
evidence-bearing tool calls must be routed back through the revise node;
cited replies and refusals must not. The router under test
(``unverified_router``) is shared by the legacy driver and the LangGraph
runtime, so these assertions cover the routing decision for both.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pytest
from llm_provider_py.types import (
    ChatMessage,
    StopReason,
    TextDelta,
    ToolStreamChunk,
)

from control_plane.agents.agent_kenny.graph import (
    NODE_ADVERSARIAL,
    NODE_REVISE,
    unverified_router,
)
from control_plane.agents.agent_kenny.nodes.revise import (
    has_evidence_tool_results,
    looks_like_refusal,
    needs_zero_citation_revision,
    revise_if_unverified,
    should_revise,
)
from control_plane.agents.agent_kenny.types import (
    MAX_REVISION_ATTEMPTS,
    AgentState,
    CitationReport,
    VerifiedCitation,
)

_EVIDENCE_RESULT = '<tool_result name="get_open_risks">{"rows":[{"kind":"summary"}],"row_count":1}</tool_result>'
_EMPTY_RESULT = '<tool_result name="query_ledger">{"rows":[],"truncated":false,"row_count":0}</tool_result>'
_ERROR_RESULT = '<tool_result name="walk_chain" error="true">tool_error: bad input</tool_result>'


def _state(
    *,
    text: str = "",
    report: CitationReport | None = None,
    tool_messages: list[str] | None = None,
    attempts: int = 0,
) -> AgentState:
    s = AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="what's the state?",
        started_at=datetime(2026, 8, 11, tzinfo=UTC),
    )
    s.accumulated_text = text
    s.citation_report = report
    s.revision_attempts = attempts
    for content in tool_messages or []:
        s.messages.append({"role": "user", "content": content})
    return s


def _verified_report() -> CitationReport:
    r = CitationReport()
    r.verified.append(VerifiedCitation(kind="event", identifier=str(uuid.uuid4()), outcome="verified"))
    return r


# --- trigger conditions -------------------------------------------------------


def test_uncited_factual_reply_with_evidence_triggers_revision() -> None:
    s = _state(
        text="Two open risks remain and the cutover slipped a sprint.",
        report=CitationReport(),
        tool_messages=[_EVIDENCE_RESULT],
    )
    assert needs_zero_citation_revision(s) is True
    assert should_revise(s) is True
    assert unverified_router(s) == NODE_REVISE


def test_cited_reply_does_not_trigger_revision() -> None:
    s = _state(
        text="Two open risks remain [event:11111111-1111-4111-8111-111111111111].",
        report=_verified_report(),
        tool_messages=[_EVIDENCE_RESULT],
    )
    assert needs_zero_citation_revision(s) is False
    assert should_revise(s) is False
    assert unverified_router(s) == NODE_ADVERSARIAL


def test_refusal_without_citations_does_not_trigger_revision() -> None:
    s = _state(
        text="I don't know — there is no relevant data in this engagement.",
        report=CitationReport(),
        tool_messages=[_EVIDENCE_RESULT],
    )
    assert needs_zero_citation_revision(s) is False
    assert should_revise(s) is False
    assert unverified_router(s) == NODE_ADVERSARIAL


def test_uncited_reply_without_tool_evidence_does_not_trigger_revision() -> None:
    s = _state(text="Everything looks fine.", report=CitationReport())
    assert needs_zero_citation_revision(s) is False
    assert unverified_router(s) == NODE_ADVERSARIAL


def test_empty_rows_and_error_results_are_not_evidence() -> None:
    s = _state(
        text="Everything looks fine.",
        report=CitationReport(),
        tool_messages=[_EMPTY_RESULT, _ERROR_RESULT],
    )
    assert has_evidence_tool_results(s) is False
    assert needs_zero_citation_revision(s) is False


def test_external_envelope_body_counts_as_evidence() -> None:
    s = _state(
        text="The launch thread agreed on Friday.",
        report=CitationReport(),
        tool_messages=[
            '<tool_result name="slack__search"><external_data source="slack" tool="search">'
            "thread: launch friday</external_data></tool_result>"
        ],
    )
    assert has_evidence_tool_results(s) is True
    assert needs_zero_citation_revision(s) is True


def test_trigger_respects_max_revision_attempts() -> None:
    s = _state(
        text="Two open risks remain.",
        report=CitationReport(),
        tool_messages=[_EVIDENCE_RESULT],
        attempts=MAX_REVISION_ATTEMPTS,
    )
    assert needs_zero_citation_revision(s) is False
    assert should_revise(s) is False
    assert unverified_router(s) == NODE_ADVERSARIAL


def test_placeholder_replies_do_not_trigger_revision() -> None:
    for placeholder in ("(no response)", "(tool-call cap reached)", ""):
        s = _state(text=placeholder, report=CitationReport(), tool_messages=[_EVIDENCE_RESULT])
        assert needs_zero_citation_revision(s) is False, placeholder


def test_unverified_citations_still_trigger_revision() -> None:
    report = CitationReport()
    report.not_found.append(VerifiedCitation(kind="event", identifier=str(uuid.uuid4()), outcome="not_found"))
    s = _state(text="See [event:x].", report=report)
    assert should_revise(s) is True
    assert unverified_router(s) == NODE_REVISE


def test_looks_like_refusal_patterns() -> None:
    assert looks_like_refusal("") is True
    assert looks_like_refusal("I cannot answer that from the substrate.") is True
    assert looks_like_refusal("There is insufficient data to say.") is True
    assert looks_like_refusal("The cutover slipped a sprint.") is False


# --- revise node behaviour ----------------------------------------------------


class _FakeProvider:
    id = "fake"

    def __init__(self, reply: str) -> None:
        self._reply = reply
        self.calls = 0
        self.last_messages: list[ChatMessage] | None = None

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = tools, temperature, max_output_tokens
        self.calls += 1
        self.last_messages = messages
        yield TextDelta(content=self._reply)
        yield StopReason(reason="end_turn", usage={"input_tokens": 5, "output_tokens": 5})


@pytest.mark.asyncio
async def test_revise_appends_zero_citation_instruction_and_recalls_llm() -> None:
    cited = "Two open risks remain [event:11111111-1111-4111-8111-111111111111]."
    provider = _FakeProvider(reply=cited)
    s = _state(
        text="Two open risks remain.",
        report=CitationReport(),
        tool_messages=[_EVIDENCE_RESULT],
    )
    await revise_if_unverified(provider, s)
    assert provider.calls == 1
    assert s.revision_attempts == 1
    assert s.accumulated_text == cited
    corrective = [
        m
        for m in s.messages
        if m.get("role") == "user"
        and isinstance(m.get("content"), str)
        and "without any [kind:UUID] citation markers" in m["content"]
    ]
    assert len(corrective) == 1
    assert "do not add new claims" in corrective[0]["content"]


@pytest.mark.asyncio
async def test_revise_is_noop_for_cited_reply() -> None:
    provider = _FakeProvider(reply="unused")
    s = _state(
        text="Cited already [event:11111111-1111-4111-8111-111111111111].",
        report=_verified_report(),
        tool_messages=[_EVIDENCE_RESULT],
    )
    await revise_if_unverified(provider, s)
    assert provider.calls == 0
    assert s.revision_attempts == 0


@pytest.mark.asyncio
async def test_revise_keeps_unverified_instruction_for_bad_citations() -> None:
    bogus = str(uuid.uuid4())
    report = CitationReport()
    report.not_found.append(VerifiedCitation(kind="event", identifier=bogus, outcome="not_found"))
    provider = _FakeProvider(reply="Fixed.")
    s = _state(text=f"See [event:{bogus}].", report=report)
    await revise_if_unverified(provider, s)
    assert provider.calls == 1
    corrective = [
        m
        for m in s.messages
        if m.get("role") == "user" and isinstance(m.get("content"), str) and "do not resolve" in m["content"]
    ]
    assert len(corrective) == 1
    assert bogus in corrective[0]["content"]
