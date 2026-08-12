"""Cap-truncated tool batches must never leave dangling ``tool_use`` ids.

Prod incident (2026-08-11): one assistant turn requested 10 tool calls,
``MAX_TOOL_CALLS_PER_TURN=8`` truncated execution, and the next LLM call
failed with Anthropic 400 "``tool_use`` ids were found without
``tool_result`` blocks immediately after". These tests pin the fix:
every truncation path (dispatch cap, post-cap drain, revision) now
synthesizes an is_error tool_result for each unexecuted call.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from llm_provider_py.types import (
    ChatMessage,
    StopReason,
    ToolStreamChunk,
    ToolUseEnd,
    ToolUseStart,
)
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.nodes.llm_call import _build_messages
from control_plane.agents.agent_kenny.nodes.revise import revise_if_unverified
from control_plane.agents.agent_kenny.nodes.tool_dispatch import (
    TOOL_CAP_REACHED_TEXT,
    dispatch_tools,
    synthesize_unexecuted_tool_results,
)
from control_plane.agents.agent_kenny.types import (
    MAX_TOOL_CALLS_PER_TURN,
    AgentState,
    CitationReport,
    ToolResultChunk,
    VerifiedCitation,
)


def _state() -> AgentState:
    return AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="what's the state?",
        started_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


def _seed_tool_use_batch(state: AgentState, count: int, name: str = "no_such_tool") -> list[str]:
    """Record one assistant turn with ``count`` tool_use blocks + pending calls."""
    ids = [f"toolu_cap_{i}" for i in range(count)]
    state.messages.append(
        {
            "role": "assistant",
            "content": [{"type": "tool_use", "id": tid, "name": name, "input": {}} for tid in ids],
        }
    )
    state.pending_tool_calls = [{"name": name, "input": {}, "_tool_use_id": tid} for tid in ids]
    return ids


def _assert_every_tool_use_answered(msgs: list[ChatMessage]) -> None:
    """Mimic the Anthropic Messages API check that 400'd in production."""
    for i, msg in enumerate(msgs):
        content = msg.get("content")
        if msg.get("role") != "assistant" or not isinstance(content, list):
            continue
        ids = [b["id"] for b in content if isinstance(b, dict) and b.get("type") == "tool_use"]
        if not ids:
            continue
        assert i + 1 < len(msgs), f"dangling tool_use ids {ids} at end of history"
        nxt = msgs[i + 1]
        nxt_content = nxt.get("content")
        assert nxt.get("role") == "user" and isinstance(nxt_content, list), (
            f"tool_use ids {ids} not followed by a tool_result user message"
        )
        answered = {b.get("tool_use_id") for b in nxt_content if isinstance(b, dict) and b.get("type") == "tool_result"}
        assert answered == set(ids), f"unanswered tool_use ids: {set(ids) - answered}"


@pytest.mark.asyncio
async def test_dispatch_cap_truncation_synthesizes_results_for_skipped_calls() -> None:
    """Prod shape: batch larger than the remaining budget → every skipped
    call still gets an is_error tool_result, ordinally after the executed ones."""
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN - 2  # room for 2 of 4
    ids = _seed_tool_use_batch(state, 4)
    emitted: list[Any] = []

    async def sink(chunk: Any) -> None:
        emitted.append(chunk)

    # Unknown tool names never touch the DB session, so None is safe here.
    await dispatch_tools(cast(AsyncSession, None), state, emit=sink)

    assert state.pending_tool_calls == []
    assert state.tool_calls_made == MAX_TOOL_CALLS_PER_TURN
    results = [m for m in state.messages if m["role"] == "user"]
    assert len(results) == 4  # 2 executed (unknown_tool errors) + 2 synthesized
    for m in results[2:]:
        assert TOOL_CAP_REACHED_TEXT in m["content"]
        assert 'error="true"' in m["content"]
    cap_frames = [c for c in emitted if isinstance(c, ToolResultChunk) and c.error == "tool_call_cap_reached"]
    assert len(cap_frames) == 2

    # The rebuilt native history answers all 4 tool_use ids.
    msgs = _build_messages(state)
    _assert_every_tool_use_answered(msgs)
    paired = next(m for m in msgs if m["role"] == "user" and isinstance(m["content"], list))
    assert [b["tool_use_id"] for b in paired["content"]] == ids


@pytest.mark.asyncio
async def test_dispatch_at_cap_synthesizes_results_for_entire_batch() -> None:
    """Budget already exhausted before dispatch: the whole batch is synthesized."""
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    _seed_tool_use_batch(state, 3)

    await dispatch_tools(cast(AsyncSession, None), state, emit=None)

    assert state.pending_tool_calls == []
    assert state.tool_calls_made == MAX_TOOL_CALLS_PER_TURN
    results = [m for m in state.messages if m["role"] == "user"]
    assert len(results) == 3
    assert all(TOOL_CAP_REACHED_TEXT in m["content"] for m in results)
    _assert_every_tool_use_answered(_build_messages(state))


@pytest.mark.asyncio
async def test_synthesize_helper_answers_each_call_and_emits_frames() -> None:
    state = _state()
    calls = [{"name": "keyword_search", "input": {}, "_tool_use_id": "toolu_x"}]
    emitted: list[Any] = []

    async def sink(chunk: Any) -> None:
        emitted.append(chunk)

    await synthesize_unexecuted_tool_results(state, calls, sink, reason='custom "reason"', error_code="custom_code")
    assert len(state.messages) == 1
    content = state.messages[0]["content"]
    assert "custom 'reason'" in content  # double quotes sanitized
    assert '<tool_result name="keyword_search" error="true">' in content
    assert [c.error for c in emitted if isinstance(c, ToolResultChunk)] == ["custom_code"]


class _FakeProvider:
    """Scripted ToolStreamChunk provider (same shape as test_kenny_native_tool_use)."""

    id = "fake"

    def __init__(self, scripts: list[list[ToolStreamChunk]]) -> None:
        self._scripts = scripts
        self.calls = 0
        self.tools_messages: list[list[ChatMessage]] = []

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = tools, temperature, max_output_tokens
        self.tools_messages.append(messages)
        idx = self.calls
        self.calls += 1
        script = self._scripts[idx] if idx < len(self._scripts) else []
        for chunk in script:
            yield chunk


@pytest.mark.asyncio
async def test_revision_call_that_emits_tool_use_gets_synthesized_results() -> None:
    """The revision loop never dispatches tools — a revision reply made of
    tool_use blocks must still leave well-formed history for attempt 2."""
    state = _state()
    state.citation_report = CitationReport(
        not_found=[VerifiedCitation(kind="event", identifier=str(uuid.uuid4()), outcome="not_found")]
    )
    provider = _FakeProvider(
        scripts=[
            [
                ToolUseStart(id="toolu_rev", name="keyword_search"),
                ToolUseEnd(id="toolu_rev", name="keyword_search", input={"query": "risk"}),
                StopReason(reason="tool_use", usage={"input_tokens": 5, "output_tokens": 5}),
            ]
        ]
    )

    await revise_if_unverified(provider, state, emit=None)

    assert state.revision_attempts == 1
    assert state.pending_tool_calls == []
    synthesized = [m for m in state.messages if m["role"] == "user" and "tool_result" in str(m["content"])]
    assert len(synthesized) == 1
    assert "not available while revising" in synthesized[0]["content"]
    _assert_every_tool_use_answered(_build_messages(state))
