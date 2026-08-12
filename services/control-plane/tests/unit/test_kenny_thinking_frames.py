"""Node-level tests: provider ThinkingDelta chunks → SSE `thinking` frames.

The llm_call node buffers native extended-thinking deltas per block and
emits one :class:`ThinkingChunk` per block, gated by
``DEPLOYAI_AGENT_THINKING_BUDGET`` (0 / unset = off, no behaviour change).
``stream.format_chunk`` renders ThinkingChunk as the ``thinking`` SSE
frame with the ``{"content": ...}`` payload OracleChat.client.tsx parses.
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
    ThinkingDelta,
    ToolStreamChunk,
    ToolUseEnd,
    ToolUseStart,
)

from control_plane.agents.agent_kenny.nodes.llm_call import call_llm_with_tools
from control_plane.agents.agent_kenny.stream import format_chunk
from control_plane.agents.agent_kenny.types import (
    AgentState,
    DeltaChunk,
    ThinkingChunk,
    ToolCallChunk,
)


def _state() -> AgentState:
    return AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="what's the state?",
        started_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


class _FakeProvider:
    id = "fake"

    def __init__(self, script: list[ToolStreamChunk]) -> None:
        self._script = script

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = messages, tools, temperature, max_output_tokens
        for chunk in self._script:
            yield chunk


_SCRIPT: list[ToolStreamChunk] = [
    ThinkingDelta(content="Plan: "),
    ThinkingDelta(content="check the open risks."),
    TextDelta(content="Two risks remain."),
    StopReason(reason="end_turn", usage={"input_tokens": 5, "output_tokens": 5}),
]


async def _run(script: list[ToolStreamChunk]) -> tuple[AgentState, list[Any]]:
    state = _state()
    emitted: list[Any] = []

    async def sink(chunk: Any) -> None:
        emitted.append(chunk)

    await call_llm_with_tools(_FakeProvider(script), state, emit=sink)
    return state, emitted


@pytest.mark.asyncio
async def test_thinking_frames_emitted_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_AGENT_THINKING_BUDGET", "2048")
    state, emitted = await _run(_SCRIPT)
    thinking = [c for c in emitted if isinstance(c, ThinkingChunk)]
    assert [c.content for c in thinking] == ["Plan: check the open risks."]
    # Frame ordering: the thinking frame streams before the first delta.
    assert emitted.index(thinking[0]) < emitted.index(next(c for c in emitted if isinstance(c, DeltaChunk)))
    # Thinking never leaks into the visible reply.
    assert state.accumulated_text == "Two risks remain."


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [None, "0", "-1", "banana"])
async def test_thinking_frames_absent_when_disabled(monkeypatch: pytest.MonkeyPatch, raw: str | None) -> None:
    if raw is None:
        monkeypatch.delenv("DEPLOYAI_AGENT_THINKING_BUDGET", raising=False)
    else:
        monkeypatch.setenv("DEPLOYAI_AGENT_THINKING_BUDGET", raw)
    state, emitted = await _run(_SCRIPT)
    assert not [c for c in emitted if isinstance(c, ThinkingChunk)]
    assert state.accumulated_text == "Two risks remain."


@pytest.mark.asyncio
async def test_thinking_flushes_before_tool_call_frames(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_AGENT_THINKING_BUDGET", "1024")
    script: list[ToolStreamChunk] = [
        ThinkingDelta(content="Need the ledger."),
        ToolUseStart(id="toolu_1", name="query_ledger"),
        ToolUseEnd(id="toolu_1", name="query_ledger", input={"limit": 5}),
        StopReason(reason="tool_use", usage={}),
    ]
    state, emitted = await _run(script)
    thinking = [c for c in emitted if isinstance(c, ThinkingChunk)]
    assert [c.content for c in thinking] == ["Need the ledger."]
    tool_call = next(c for c in emitted if isinstance(c, ToolCallChunk))
    assert emitted.index(thinking[0]) < emitted.index(tool_call)
    assert state.pending_tool_calls and state.pending_tool_calls[0]["name"] == "query_ledger"


@pytest.mark.asyncio
async def test_thinking_frame_capped_at_500_chars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_AGENT_THINKING_BUDGET", "2048")
    long_script: list[ToolStreamChunk] = [
        ThinkingDelta(content="x" * 400),
        ThinkingDelta(content="y" * 400),
        TextDelta(content="done"),
        StopReason(reason="end_turn", usage={}),
    ]
    _, emitted = await _run(long_script)
    thinking = [c for c in emitted if isinstance(c, ThinkingChunk)]
    assert len(thinking) == 1
    assert len(thinking[0].content) == 500


def test_thinking_chunk_renders_expected_sse_frame() -> None:
    frame = format_chunk(ThinkingChunk(content="Plan: check risks."))
    assert frame == b'event: thinking\ndata: {"content":"Plan: check risks."}\n\n'
