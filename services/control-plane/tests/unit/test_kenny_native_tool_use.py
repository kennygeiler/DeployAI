"""Unit tests for Agent Kenny v2 Phase 2 follow-up — native tool_use protocol."""

from __future__ import annotations

import asyncio
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
    ToolUseEnd,
    ToolUseStart,
)

from control_plane.agents.agent_kenny.nodes.llm_call import (
    _build_messages,
    call_llm_with_tools,
    call_llm_with_tools_sync,
)
from control_plane.agents.agent_kenny.types import (
    AgentState,
    DeltaChunk,
    ToolCallChunk,
)
from control_plane.agents.tools import TOOL_REGISTRY


def _state() -> AgentState:
    return AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="what's the state?",
        started_at=datetime(2026, 5, 23, tzinfo=UTC),
    )


class _FakeProvider:
    """Drive the llm_call node with a scripted sequence of ToolStreamChunk lists."""

    id = "fake"

    def __init__(self, scripts: list[list[ToolStreamChunk]]) -> None:
        self._scripts = scripts
        self.calls = 0
        self.last_messages: list[ChatMessage] | None = None
        self.last_tools: list[dict[str, Any]] | None = None

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = temperature, max_output_tokens
        self.last_messages = messages
        self.last_tools = tools
        idx = self.calls
        self.calls += 1
        script = self._scripts[idx] if idx < len(self._scripts) else []
        for chunk in script:
            yield chunk


@pytest.mark.asyncio
async def test_call_llm_with_tools_consumes_text_only_turn() -> None:
    state = _state()
    provider = _FakeProvider(
        scripts=[
            [
                TextDelta(content="Final answer."),
                StopReason(reason="end_turn", usage={"input_tokens": 5, "output_tokens": 3}),
            ]
        ]
    )
    emitted: list[Any] = []

    async def sink(chunk: Any) -> None:
        emitted.append(chunk)

    await call_llm_with_tools(provider, state, emit=sink)
    assert state.pending_tool_calls == []
    assert state.accumulated_text == "Final answer."
    assert state.last_text == "Final answer."
    assert state.final_tokens == 8
    assert any(isinstance(c, DeltaChunk) and c.content == "Final answer." for c in emitted)


@pytest.mark.asyncio
async def test_call_llm_with_tools_captures_tool_use_blocks() -> None:
    state = _state()
    provider = _FakeProvider(
        scripts=[
            [
                ToolUseStart(id="toolu_1", name="get_engagement_summary"),
                ToolUseEnd(id="toolu_1", name="get_engagement_summary", input={}),
                StopReason(reason="tool_use", usage={"input_tokens": 12, "output_tokens": 6}),
            ]
        ]
    )
    emitted: list[Any] = []

    async def sink(chunk: Any) -> None:
        emitted.append(chunk)

    await call_llm_with_tools(provider, state, emit=sink)
    assert state.pending_tool_calls == [
        {"name": "get_engagement_summary", "input": {}, "_tool_use_id": "toolu_1"}
    ]
    # assistant message persisted with native tool_use block.
    assert len(state.messages) == 1
    assistant = state.messages[0]
    assert assistant["role"] == "assistant"
    blocks = assistant["content"]
    assert isinstance(blocks, list)
    tool_use_blocks = [b for b in blocks if b.get("type") == "tool_use"]
    assert tool_use_blocks == [
        {"type": "tool_use", "id": "toolu_1", "name": "get_engagement_summary", "input": {}}
    ]
    assert state.final_tokens == 18
    assert any(isinstance(c, ToolCallChunk) and c.name == "get_engagement_summary" for c in emitted)


@pytest.mark.asyncio
async def test_call_llm_with_tools_passes_tool_registry_to_provider() -> None:
    state = _state()
    provider = _FakeProvider(
        scripts=[
            [StopReason(reason="end_turn", usage={"input_tokens": 1, "output_tokens": 1})]
        ]
    )
    await call_llm_with_tools_sync(provider, state)
    assert provider.last_tools is not None
    tool_names = {t["name"] for t in provider.last_tools}
    assert tool_names == set(TOOL_REGISTRY.keys())
    sample = provider.last_tools[0]
    assert "input_schema" in sample
    assert "description" in sample


@pytest.mark.asyncio
async def test_build_messages_pairs_tool_result_text_with_tool_use_ids() -> None:
    """Simulate dispatcher leftover: assistant tool_use turn + user tool_result text.

    The next call's _build_messages should rebuild the native pairing.
    """
    state = _state()
    # Assistant message synthesized by a previous llm_call.
    state.messages.append(
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_99", "name": "get_engagement_summary", "input": {}}
            ],
        }
    )
    # User-text message tool_dispatch appended (existing string protocol).
    state.messages.append(
        {
            "role": "user",
            "content": '<tool_result name="get_engagement_summary">{"rows":[],"row_count":0}</tool_result>',
        }
    )

    msgs = _build_messages(state)
    # msgs ends with the current user_message; the synthesized pair is at -3, -2.
    assistant_msg = next(m for m in msgs if m["role"] == "assistant" and isinstance(m["content"], list))
    user_with_result = next(
        m
        for m in msgs
        if m["role"] == "user"
        and isinstance(m["content"], list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
    )
    assistant_blocks = assistant_msg["content"]
    tool_use = next(b for b in assistant_blocks if b.get("type") == "tool_use")
    assert tool_use["id"] == "toolu_99"
    result_blocks = user_with_result["content"]
    assert len(result_blocks) == 1
    assert result_blocks[0]["tool_use_id"] == "toolu_99"
    assert "row_count" in result_blocks[0]["content"]


@pytest.mark.asyncio
async def test_build_messages_marks_tool_error_results() -> None:
    state = _state()
    state.messages.append(
        {
            "role": "assistant",
            "content": [
                {"type": "tool_use", "id": "toolu_err", "name": "walk_chain", "input": {}}
            ],
        }
    )
    state.messages.append(
        {
            "role": "user",
            "content": (
                '<tool_result name="walk_chain" error="tool_error: bad input">'
                "tool_error: bad input</tool_result>"
            ),
        }
    )
    msgs = _build_messages(state)
    user_msg = next(
        m
        for m in msgs
        if m["role"] == "user"
        and isinstance(m["content"], list)
        and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
    )
    assert user_msg["content"][0]["is_error"] is True


@pytest.mark.asyncio
async def test_call_llm_with_tools_multi_turn_loops_back_with_tool_result() -> None:
    """Two LLM calls + a tool_dispatch in between; second call sees the result."""
    state = _state()
    provider = _FakeProvider(
        scripts=[
            [
                ToolUseStart(id="toolu_a", name="get_engagement_summary"),
                ToolUseEnd(id="toolu_a", name="get_engagement_summary", input={}),
                StopReason(reason="tool_use", usage={"input_tokens": 5, "output_tokens": 5}),
            ],
            [
                TextDelta(content="Done. [event:11111111-1111-4111-8111-111111111111]"),
                StopReason(reason="end_turn", usage={"input_tokens": 4, "output_tokens": 6}),
            ],
        ]
    )
    # Turn 1: emits tool_use.
    await call_llm_with_tools(provider, state, emit=None)
    assert state.pending_tool_calls and state.pending_tool_calls[0]["_tool_use_id"] == "toolu_a"
    # Simulate tool_dispatch appending the tool_result text + clearing pending.
    state.messages.append(
        {
            "role": "user",
            "content": '<tool_result name="get_engagement_summary">{"rows":[],"row_count":0}</tool_result>',
        }
    )
    state.pending_tool_calls = []
    # Turn 2: emits final text.
    await call_llm_with_tools(provider, state, emit=None)
    assert state.pending_tool_calls == []
    assert "[event:" in state.accumulated_text
    # The provider's second call must have received a properly paired native
    # tool_use + tool_result sequence.
    sent_msgs = provider.last_messages or []
    paired = [m for m in sent_msgs if isinstance(m.get("content"), list)]
    has_tool_use = any(
        any(isinstance(b, dict) and b.get("type") == "tool_use" for b in m["content"])
        for m in paired
    )
    has_tool_result = any(
        any(isinstance(b, dict) and b.get("type") == "tool_result" for b in m["content"])
        for m in paired
    )
    assert has_tool_use and has_tool_result


def test_call_llm_with_tools_sync_returns_state() -> None:
    state = _state()
    provider = _FakeProvider(
        scripts=[[TextDelta(content="hi"), StopReason(reason="end_turn", usage={})]]
    )
    out = asyncio.run(call_llm_with_tools_sync(provider, state))
    assert out is state
    assert state.accumulated_text == "hi"
