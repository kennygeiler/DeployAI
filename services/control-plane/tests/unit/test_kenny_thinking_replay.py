"""Node-level tests: signed thinking blocks are replayed on the follow-up call.

The Anthropic API requires that when thinking is enabled and an assistant
turn contains tool_use blocks, the SAME assistant message replayed on the
follow-up request must start with its original thinking block including
its signature. The llm_call node captures the full thinking block
(content + signature, from the provider's ThinkingDelta/ThinkingSignature
chunks) and prepends it to the synthesized assistant tool_use message in
``state.messages``; ``_native_messages`` forwards it verbatim.
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
    ThinkingSignature,
    ToolStreamChunk,
    ToolUseEnd,
    ToolUseStart,
)

from control_plane.agents.agent_kenny.nodes.llm_call import call_llm_with_tools
from control_plane.agents.agent_kenny.types import AgentState, ThinkingChunk


def _state() -> AgentState:
    return AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="what's the state?",
        started_at=datetime(2026, 8, 11, tzinfo=UTC),
    )


class _CapturingProvider:
    """Yields a fixed script per call and records the messages it was given."""

    id = "fake"

    def __init__(self, scripts: list[list[ToolStreamChunk]]) -> None:
        self._scripts = scripts
        self._calls = 0
        self.captured_messages: list[list[ChatMessage]] = []

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = tools, temperature, max_output_tokens
        self.captured_messages.append([dict(m) for m in messages])
        script = self._scripts[min(self._calls, len(self._scripts) - 1)]
        self._calls += 1
        for chunk in script:
            yield chunk


_THINKING_TOOL_SCRIPT: list[ToolStreamChunk] = [
    ThinkingDelta(content="Need the "),
    ThinkingDelta(content="ledger first."),
    ThinkingSignature(signature="sig=="),
    ToolUseStart(id="toolu_1", name="query_ledger"),
    ToolUseEnd(id="toolu_1", name="query_ledger", input={"limit": 5}),
    StopReason(reason="tool_use", usage={"input_tokens": 5, "output_tokens": 5}),
]

_FINAL_SCRIPT: list[ToolStreamChunk] = [
    TextDelta(content="Two risks remain."),
    StopReason(reason="end_turn", usage={"input_tokens": 5, "output_tokens": 5}),
]


@pytest.mark.asyncio
async def test_signed_thinking_block_prepended_to_assistant_tool_use_message() -> None:
    provider = _CapturingProvider([_THINKING_TOOL_SCRIPT])
    state = _state()
    await call_llm_with_tools(provider, state, emit=None)

    assert state.pending_tool_calls and state.pending_tool_calls[0]["name"] == "query_ledger"
    content = state.messages[-1]["content"]
    assert state.messages[-1]["role"] == "assistant"
    # Thinking block first, full content + signature, then the tool_use block.
    assert content[0] == {"type": "thinking", "thinking": "Need the ledger first.", "signature": "sig=="}
    assert content[1]["type"] == "tool_use"
    assert content[1]["id"] == "toolu_1"


@pytest.mark.asyncio
async def test_follow_up_request_carries_thinking_block_first_in_assistant_turn() -> None:
    provider = _CapturingProvider([_THINKING_TOOL_SCRIPT, _FINAL_SCRIPT])
    state = _state()
    await call_llm_with_tools(provider, state, emit=None)
    # Simulate tool_dispatch appending the result as user text.
    state.messages.append(
        {"role": "user", "content": '<tool_result name="query_ledger">3 events</tool_result>'}
    )
    await call_llm_with_tools(provider, state, emit=None)

    follow_up = provider.captured_messages[1]
    assistant_turns = [m for m in follow_up if m["role"] == "assistant" and isinstance(m["content"], list)]
    assert len(assistant_turns) == 1
    content = assistant_turns[0]["content"]
    assert content[0] == {"type": "thinking", "thinking": "Need the ledger first.", "signature": "sig=="}
    assert content[1]["type"] == "tool_use"
    # The trailing user tool_result was repacked into a native block and
    # still pairs with the tool_use id.
    tool_results = [m for m in follow_up if m["role"] == "user" and isinstance(m["content"], list)]
    assert tool_results[0]["content"][0]["tool_use_id"] == "toolu_1"


@pytest.mark.asyncio
async def test_thinking_replay_captured_even_when_sse_frames_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Replay capture is a correctness requirement, not a UI feature — it must
    run even when DEPLOYAI_AGENT_THINKING_BUDGET keeps SSE frames off."""
    monkeypatch.delenv("DEPLOYAI_AGENT_THINKING_BUDGET", raising=False)
    provider = _CapturingProvider([_THINKING_TOOL_SCRIPT])
    state = _state()
    emitted: list[Any] = []

    async def sink(chunk: Any) -> None:
        emitted.append(chunk)

    await call_llm_with_tools(provider, state, emit=sink)
    assert not [c for c in emitted if isinstance(c, ThinkingChunk)]
    assert state.messages[-1]["content"][0]["type"] == "thinking"


@pytest.mark.asyncio
async def test_thinking_replay_not_capped_at_frame_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    """SSE frames cap at 500 chars; the replayed block must stay verbatim."""
    monkeypatch.setenv("DEPLOYAI_AGENT_THINKING_BUDGET", "2048")
    long_thinking = "x" * 800
    script: list[ToolStreamChunk] = [
        ThinkingDelta(content=long_thinking),
        ThinkingSignature(signature="sig=="),
        ToolUseStart(id="toolu_1", name="query_ledger"),
        ToolUseEnd(id="toolu_1", name="query_ledger", input={}),
        StopReason(reason="tool_use", usage={}),
    ]
    provider = _CapturingProvider([script])
    state = _state()
    emitted: list[Any] = []

    async def sink(chunk: Any) -> None:
        emitted.append(chunk)

    await call_llm_with_tools(provider, state, emit=sink)
    frames = [c for c in emitted if isinstance(c, ThinkingChunk)]
    assert len(frames) == 1 and len(frames[0].content) == 500
    assert state.messages[-1]["content"][0]["thinking"] == long_thinking


@pytest.mark.asyncio
async def test_unsigned_thinking_block_not_replayed() -> None:
    """A block that never received a signature can't be replayed — the API
    would reject it — so it is dropped from the synthesized message."""
    script: list[ToolStreamChunk] = [
        ThinkingDelta(content="orphan"),
        ToolUseStart(id="toolu_1", name="query_ledger"),
        ToolUseEnd(id="toolu_1", name="query_ledger", input={}),
        StopReason(reason="tool_use", usage={}),
    ]
    provider = _CapturingProvider([script])
    state = _state()
    await call_llm_with_tools(provider, state, emit=None)
    assert state.messages[-1]["content"][0]["type"] == "tool_use"
