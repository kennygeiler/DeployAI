"""Cap-final answer unit tests (prod bug, 2026-08-11).

A search-heavy turn that hit ``MAX_TOOL_CALLS_PER_TURN`` used to END with
final_text "(tool-call cap reached)" — the synthesized tool_results landed
but no further LLM call was made. The fix routes back to ``llm_call``
exactly once with ``tool_choice={"type": "none"}`` so the model produces a
real answer. These tests pin the flag lifecycle (``tools_exhausted`` /
``cap_final_call_made``), the shared :func:`enforce_tool_call_cap` guard,
and the ``tool_choice`` wiring in :func:`call_llm_with_tools`.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any, cast

import pytest
from llm_provider_py.types import (
    ChatMessage,
    LLMProvider,
    StopReason,
    TextDelta,
    ToolStreamChunk,
)

from control_plane.agents.agent_kenny.nodes.llm_call import call_llm_with_tools
from control_plane.agents.agent_kenny.nodes.tool_dispatch import (
    TOOL_CAP_REACHED_TEXT,
    enforce_tool_call_cap,
)
from control_plane.agents.agent_kenny.types import (
    MAX_TOOL_CALLS_PER_TURN,
    AgentState,
    ToolResultChunk,
)


def _state() -> AgentState:
    return AgentState(
        tenant_id=uuid.uuid4(),
        engagement_id=uuid.uuid4(),
        actor_user_id=uuid.uuid4(),
        user_message="what's the state?",
        started_at=datetime(2026, 8, 12, tzinfo=UTC),
    )


# --- enforce_tool_call_cap ----------------------------------------------------


@pytest.mark.asyncio
async def test_enforce_is_noop_under_the_cap() -> None:
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN - 1
    state.pending_tool_calls = [{"name": "query_ledger", "input": {}, "_tool_use_id": "t1"}]

    await enforce_tool_call_cap(state)

    assert state.pending_tool_calls  # untouched
    assert state.tools_exhausted is False
    assert state.accumulated_text == ""


@pytest.mark.asyncio
async def test_enforce_at_cap_drains_pending_and_schedules_final_call() -> None:
    """At the cap with drained intents: synthesize results, flag the
    cap-final call, and do NOT stamp the placeholder — the real answer is
    still ahead (the placeholder-here behaviour WAS the prod bug)."""
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    state.pending_tool_calls = [{"name": "keyword_search", "input": {}, "_tool_use_id": "t1"}]
    emitted: list[Any] = []

    async def sink(chunk: Any) -> None:
        emitted.append(chunk)

    await enforce_tool_call_cap(state, sink)

    assert state.pending_tool_calls == []
    assert state.tools_exhausted is True
    assert state.cap_final_call_made is False
    assert state.accumulated_text == ""  # no placeholder before the final call
    assert any(TOOL_CAP_REACHED_TEXT in str(m.get("content")) for m in state.messages)
    assert [c.error for c in emitted if isinstance(c, ToolResultChunk)] == ["tool_call_cap_reached"]


@pytest.mark.asyncio
async def test_enforce_after_final_call_salvages_placeholder_only_if_empty() -> None:
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    state.tools_exhausted = True
    state.cap_final_call_made = True
    state.accumulated_text = ""
    state.last_text = ""

    await enforce_tool_call_cap(state)

    assert state.accumulated_text == "(tool-call cap reached)"


@pytest.mark.asyncio
async def test_enforce_after_final_call_keeps_real_answer() -> None:
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    state.tools_exhausted = True
    state.cap_final_call_made = True
    state.accumulated_text = "a real cited answer [event:abc]"

    await enforce_tool_call_cap(state)

    assert state.accumulated_text == "a real cited answer [event:abc]"


@pytest.mark.asyncio
async def test_enforce_does_not_reschedule_after_final_call() -> None:
    """A misbehaving provider proposing tools on the no-tools call gets its
    intents drained, but the final call is never re-armed — no loop."""
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    state.tools_exhausted = True
    state.cap_final_call_made = True
    state.pending_tool_calls = [{"name": "query_ledger", "input": {}, "_tool_use_id": "t2"}]

    await enforce_tool_call_cap(state)

    assert state.pending_tool_calls == []
    # tools_exhausted stays True but cap_final_call_made keeps the router
    # from routing back to llm_call (see test_agent_kenny_graph_routing).
    assert state.cap_final_call_made is True
    assert state.accumulated_text == "(tool-call cap reached)"


@pytest.mark.asyncio
async def test_enforce_at_cap_without_pending_keeps_model_text() -> None:
    """The model stopped requesting tools on its own at the cap — its text
    ships; no extra LLM call is scheduled."""
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    state.accumulated_text = "final answer at the cap"

    await enforce_tool_call_cap(state)

    assert state.tools_exhausted is False
    assert state.accumulated_text == "final answer at the cap"


# --- call_llm_with_tools tool_choice wiring -----------------------------------


class _CapturingProvider:
    """Fake provider that records tool_choice and returns scripted text."""

    id = "fake-cap"

    def __init__(self, text: str = "cap-final answer [event:xyz]") -> None:
        self._text = text
        self.tool_choices: list[dict[str, Any] | None] = []

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
        tool_choice: dict[str, Any] | None = None,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = messages, temperature, max_output_tokens
        assert tools, "tools array must still be sent on the cap-final call"
        self.tool_choices.append(tool_choice)
        yield TextDelta(content=self._text)
        yield StopReason(reason="end_turn", usage={"input_tokens": 5, "output_tokens": 5})


class _NoToolChoiceProvider:
    """Fake whose signature REJECTS tool_choice — proves the kwarg is only
    passed on cap-final calls (backwards compatibility for existing fakes)."""

    id = "fake-legacy"

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = messages, tools, temperature, max_output_tokens
        yield TextDelta(content="normal answer")
        yield StopReason(reason="end_turn", usage={})


@pytest.mark.asyncio
async def test_llm_call_sends_tool_choice_none_when_tools_exhausted() -> None:
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    state.tools_exhausted = True
    provider = _CapturingProvider()

    await call_llm_with_tools(cast(LLMProvider, provider), state)

    assert provider.tool_choices == [{"type": "none"}]
    assert state.cap_final_call_made is True
    assert state.accumulated_text == "cap-final answer [event:xyz]"
    assert state.pending_tool_calls == []


@pytest.mark.asyncio
async def test_llm_call_omits_tool_choice_when_budget_remains() -> None:
    state = _state()
    provider = _NoToolChoiceProvider()

    # Would raise TypeError if the tool_choice kwarg were passed.
    await call_llm_with_tools(cast(LLMProvider, provider), state)

    assert state.cap_final_call_made is False
    assert state.accumulated_text == "normal answer"


@pytest.mark.asyncio
async def test_revision_call_after_cap_also_runs_tool_less() -> None:
    """revision calls reuse call_llm_with_tools; with tools_exhausted still
    set they must also carry tool_choice none (the budget never reopens)."""
    state = _state()
    state.tool_calls_made = MAX_TOOL_CALLS_PER_TURN
    state.tools_exhausted = True
    state.cap_final_call_made = True  # cap-final already happened
    provider = _CapturingProvider(text="revised answer [event:xyz]")

    await call_llm_with_tools(cast(LLMProvider, provider), state)

    assert provider.tool_choices == [{"type": "none"}]
    assert state.accumulated_text == "revised answer [event:xyz]"
