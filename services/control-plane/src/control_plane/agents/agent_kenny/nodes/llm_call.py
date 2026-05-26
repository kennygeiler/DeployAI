"""``call_llm_with_tools`` — issue one LLM call, parse tool intents.

We adopt a JSON-protocol contract that is *compatible with* but does not
strictly use Anthropic's native tool-use schema. The LLM either:

- emits text containing one or more ``<tool_call>{...}</tool_call>`` blocks
  the dispatcher will execute, OR
- emits plain text (the final reply).

This stays compatible with the existing :class:`LLMProvider` abstraction
(plain text streaming) and lets unit tests stub the provider with hand-
crafted responses. Phase 3 may upgrade to native Anthropic tool-use if
the per-tenant LLM provider supports it; the rest of the graph does not
care which protocol the provider speaks.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, cast

from llm_provider_py.types import ChatMessage, LLMProvider, StreamChunk

from control_plane.agents.agent_kenny.types import (
    AgentState,
    DeltaChunk,
    ThinkingChunk,
    ToolCallChunk,
)
from control_plane.agents.tools import TOOL_REGISTRY

_LLM_TEMPERATURE = 0.2
_LLM_MAX_OUTPUT_TOKENS = 800
_TOOL_CALL_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)
_THINKING_RE = re.compile(r"<thinking>(.*?)</thinking>", re.DOTALL)


def _format_tool_catalogue() -> str:
    lines: list[str] = []
    for spec in TOOL_REGISTRY.values():
        lines.append(f"- {spec.name}: {spec.description}")
    return "\n".join(lines)


def _system_prompt(state: AgentState) -> str:
    return (
        "You are Agent Kenny, the deployment co-pilot for this engagement. "
        "You answer questions grounded in the engagement substrate (ledger + "
        "matrix + insights). Cite every factual claim with [event:UUID], "
        "[node:UUID], [insight:UUID], or [turn:UUID]. If you don't know, say so "
        "— do not invent ids or facts.\n\n"
        "Available tools (call zero or more before answering):\n"
        f"{_format_tool_catalogue()}\n\n"
        "Protocol:\n"
        "- To call a tool, emit ONE OR MORE of the following blocks:\n"
        '  <tool_call>{"name": "<tool>", "input": {...}}</tool_call>\n'
        "  You may include short prose <thinking>...</thinking> around them.\n"
        "- To finalize an answer with no further tools, emit plain prose\n"
        "  (no <tool_call> blocks) terminated by the natural end of message.\n"
        "- One reply may either be tool calls OR a final answer, not both.\n\n"
        f"Initial context snapshot:\n{_render_initial_context(state)}\n"
    )


def _render_initial_context(state: AgentState) -> str:
    ic = state.initial_context or {}
    summary = ic.get("summary") or {}
    risks = ic.get("open_risks") or []
    recent = ic.get("recent_ledger") or []
    risk_lines = "\n".join(f"- [{r.get('severity')}] {r.get('title')} (id={r.get('id')})" for r in risks[:10])
    recent_lines = "\n".join(
        f"- {r.get('occurred_at')} | {r.get('source_kind')} | {(r.get('summary') or '')[:160]} [event:{r.get('id')}]"
        for r in recent[:15]
    )
    summary_line = (
        f"nodes={summary.get('total_nodes', 0)} insights={summary.get('total_insights', 0)}" if summary else "empty"
    )
    return (
        f"Engagement summary: {summary_line}\n\n"
        f"Open risks:\n{risk_lines or '(none)'}\n\n"
        f"Recent ledger:\n{recent_lines or '(none)'}\n"
    )


def _build_messages(state: AgentState) -> list[ChatMessage]:
    """Render the running conversation + tool roundtrip history as prompt."""
    out: list[ChatMessage] = [{"role": "system", "content": _system_prompt(state)}]
    for turn in state.history:
        role = turn.get("role", "user")
        if role in ("user", "assistant"):
            out.append({"role": role, "content": turn.get("content", "")})
    for msg in state.messages:
        role = msg.get("role", "user")
        if role in ("user", "assistant"):
            out.append({"role": role, "content": str(msg.get("content", ""))})
    out.append({"role": "user", "content": state.user_message})
    return out


def parse_tool_calls(text: str) -> list[dict[str, Any]]:
    """Extract zero-or-more ``<tool_call>{...}</tool_call>`` blocks."""
    found: list[dict[str, Any]] = []
    for m in _TOOL_CALL_RE.finditer(text):
        body = m.group(1).strip()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        name = payload.get("name")
        if not isinstance(name, str):
            continue
        input_obj = payload.get("input", {})
        if not isinstance(input_obj, dict):
            input_obj = {}
        found.append({"name": name, "input": input_obj})
    return found


def parse_thinking(text: str) -> list[str]:
    return [m.group(1).strip() for m in _THINKING_RE.finditer(text) if m.group(1).strip()]


def strip_protocol_blocks(text: str) -> str:
    """Remove ``<tool_call>`` + ``<thinking>`` so the user sees only the reply."""
    text = _TOOL_CALL_RE.sub("", text)
    text = _THINKING_RE.sub("", text)
    return text.strip()


async def call_llm_with_tools(
    provider: LLMProvider,
    state: AgentState,
    emit: Callable[[Any], Awaitable[None]] | None = None,
) -> AgentState:
    """Run one streamed LLM call, collect text, parse tool intents.

    ``emit`` is the async sink that the route layer feeds into its SSE
    writer. ``None`` skips streaming (unit tests).
    """
    messages = _build_messages(state)
    accumulated: list[str] = []
    tokens = 0
    stream: AsyncIterator[StreamChunk] = provider.chat_complete_stream(
        messages,
        temperature=_LLM_TEMPERATURE,
        max_output_tokens=_LLM_MAX_OUTPUT_TOKENS,
    )
    async for chunk in stream:
        if chunk.done:
            tokens = chunk.tokens_used
            break
        if chunk.delta:
            accumulated.append(chunk.delta)
            if emit is not None:
                await emit(DeltaChunk(content=chunk.delta))

    raw = "".join(accumulated)
    tool_calls = parse_tool_calls(raw)
    thinking = parse_thinking(raw)
    state.last_text = raw
    if tool_calls:
        state.pending_tool_calls = tool_calls
        if emit is not None:
            for t in thinking:
                await emit(ThinkingChunk(content=t[:500]))
            for tc in tool_calls:
                await emit(ToolCallChunk(name=str(tc.get("name", "")), input=cast(dict[str, Any], tc.get("input", {}))))
    else:
        state.pending_tool_calls = []
        state.accumulated_text = strip_protocol_blocks(raw)
        if emit is not None:
            for t in thinking:
                await emit(ThinkingChunk(content=t[:500]))
    state.final_tokens = state.final_tokens + max(tokens, 0)
    return state


async def call_llm_with_tools_sync(provider: LLMProvider, state: AgentState) -> AgentState:
    """Convenience for tests + the integration path that doesn't need streaming."""
    return await asyncio.shield(call_llm_with_tools(provider, state, emit=None))


__all__ = [
    "call_llm_with_tools",
    "call_llm_with_tools_sync",
    "parse_thinking",
    "parse_tool_calls",
    "strip_protocol_blocks",
]
