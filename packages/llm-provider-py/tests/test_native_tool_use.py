"""Native tool-use protocol contract across stub + Anthropic + OpenAI providers."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest

from llm_provider_py.anthropic import AnthropicProvider
from llm_provider_py.openai import OpenAIProvider, anthropic_tools_to_openai
from llm_provider_py.stub import create_stub_provider
from llm_provider_py.types import (
    StopReason,
    TextDelta,
    ToolStreamChunk,
    ToolUseEnd,
    ToolUseInputDelta,
    ToolUseStart,
)


_TOOL_SPEC: list[dict[str, Any]] = [
    {
        "name": "query_ledger",
        "description": "Query the ledger.",
        "input_schema": {
            "type": "object",
            "properties": {"limit": {"type": "integer"}},
            "required": [],
        },
    }
]


@pytest.mark.asyncio
async def test_stub_emits_text_when_no_script() -> None:
    p = create_stub_provider()
    p.scripted_text = ["hello world"]
    chunks: list[ToolStreamChunk] = []
    async for c in p.chat_complete_stream_with_tools([{"role": "user", "content": "hi"}], _TOOL_SPEC):
        chunks.append(c)
    assert any(isinstance(c, TextDelta) and c.content == "hello world" for c in chunks)
    assert isinstance(chunks[-1], StopReason)
    assert chunks[-1].reason == "end_turn"


@pytest.mark.asyncio
async def test_stub_emits_scripted_tool_use_sequence() -> None:
    p = create_stub_provider()
    p.scripted_tool_calls = [
        [
            {"id": "tu_1", "name": "query_ledger", "input": {"limit": 5}},
        ]
    ]
    chunks: list[ToolStreamChunk] = []
    async for c in p.chat_complete_stream_with_tools(
        [{"role": "user", "content": "hi"}],
        _TOOL_SPEC,
    ):
        chunks.append(c)
    start = next(c for c in chunks if isinstance(c, ToolUseStart))
    delta = next(c for c in chunks if isinstance(c, ToolUseInputDelta))
    end = next(c for c in chunks if isinstance(c, ToolUseEnd))
    stop = chunks[-1]
    assert start.id == "tu_1"
    assert start.name == "query_ledger"
    assert delta.partial_json == '{"limit": 5}'
    assert end.id == "tu_1"
    assert end.input == {"limit": 5}
    assert isinstance(stop, StopReason)
    assert stop.reason == "tool_use"


@pytest.mark.asyncio
async def test_stub_supports_multiple_scripted_turns() -> None:
    p = create_stub_provider()
    p.scripted_tool_calls = [
        [{"id": "tu_a", "name": "query_ledger", "input": {"limit": 3}}],
        [],
    ]
    p.scripted_text = ["", "final reply"]
    out1: list[ToolStreamChunk] = []
    async for c in p.chat_complete_stream_with_tools([{"role": "user", "content": "x"}], _TOOL_SPEC):
        out1.append(c)
    out2: list[ToolStreamChunk] = []
    async for c in p.chat_complete_stream_with_tools([{"role": "user", "content": "y"}], _TOOL_SPEC):
        out2.append(c)
    assert any(isinstance(c, ToolUseEnd) for c in out1)
    assert any(isinstance(c, TextDelta) and c.content == "final reply" for c in out2)
    assert all(not isinstance(c, ToolUseEnd) for c in out2)


@pytest.mark.asyncio
async def test_anthropic_chat_complete_stream_with_tools_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 11, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Let me check."}},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "tool_use", "id": "toolu_abc", "name": "query_ledger", "input": {}},
        },
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": '{"li'}},
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": 'mit":3}'}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 9}},
    ]

    async def fake_iter_events(self: AnthropicProvider, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        captured["body"] = body
        for ev in events:
            yield ev

    monkeypatch.setattr(AnthropicProvider, "_iter_sse_events", fake_iter_events)  # type: ignore[assignment]

    p = AnthropicProvider(api_key="sk-test")
    out: list[ToolStreamChunk] = []
    async for c in p.chat_complete_stream_with_tools(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        _TOOL_SPEC,
        temperature=0.1,
        max_output_tokens=128,
    ):
        out.append(c)

    body = captured["body"]
    assert body["stream"] is True
    assert body["max_tokens"] == 128
    assert body["temperature"] == 0.1
    assert body["tools"] == _TOOL_SPEC

    text_chunks = [c for c in out if isinstance(c, TextDelta)]
    assert text_chunks and text_chunks[0].content == "Let me check."
    starts = [c for c in out if isinstance(c, ToolUseStart)]
    assert starts == [ToolUseStart(id="toolu_abc", name="query_ledger")]
    deltas = [c for c in out if isinstance(c, ToolUseInputDelta)]
    assert deltas[0].partial_json == '{"li'
    assert deltas[1].partial_json == 'mit":3}'
    ends = [c for c in out if isinstance(c, ToolUseEnd)]
    assert ends == [ToolUseEnd(id="toolu_abc", name="query_ledger", input={"limit": 3})]
    final = out[-1]
    assert isinstance(final, StopReason)
    assert final.reason == "tool_use"
    assert final.usage["input_tokens"] == 11
    assert final.usage["output_tokens"] == 9


@pytest.mark.asyncio
async def test_anthropic_passes_through_native_content_block_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When messages already carry list-shaped content (tool_use / tool_result), pass through verbatim."""
    captured: dict[str, Any] = {}

    async def fake_iter_events(self: AnthropicProvider, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        captured["body"] = body
        yield {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 0}}

    monkeypatch.setattr(AnthropicProvider, "_iter_sse_events", fake_iter_events)  # type: ignore[assignment]
    p = AnthropicProvider(api_key="sk-test")
    tool_use_block = {"type": "tool_use", "id": "toolu_1", "name": "query_ledger", "input": {"limit": 3}}
    tool_result_block = {"type": "tool_result", "tool_use_id": "toolu_1", "content": "[]"}
    msgs: list[dict[str, Any]] = [
        {"role": "user", "content": "go"},
        {"role": "assistant", "content": [tool_use_block]},
        {"role": "user", "content": [tool_result_block]},
    ]
    async for _ in p.chat_complete_stream_with_tools(msgs, _TOOL_SPEC):
        pass
    body_msgs = captured["body"]["messages"]
    assert body_msgs[1]["content"] == [tool_use_block]
    assert body_msgs[2]["content"] == [tool_result_block]


@pytest.mark.asyncio
async def test_openai_chat_complete_stream_with_tools_raises_not_implemented() -> None:
    p = OpenAIProvider(api_key="sk-test")
    it = p.chat_complete_stream_with_tools([{"role": "user", "content": "x"}], _TOOL_SPEC)
    with pytest.raises(NotImplementedError):
        await it.__anext__()


def test_openai_shim_translates_anthropic_to_function_spec() -> None:
    anthro = [
        {
            "name": "query_ledger",
            "description": "Query ledger events.",
            "input_schema": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}, "actor_id": {"type": "string"}},
                "required": ["limit"],
            },
        },
        {
            "name": "walk_chain",
            "description": "Walk the cause chain.",
            "input_schema": {
                "type": "object",
                "properties": {"event_id": {"type": "string"}},
                "required": ["event_id"],
            },
        },
    ]
    out = anthropic_tools_to_openai(anthro)
    assert len(out) == 2
    assert out[0] == {
        "type": "function",
        "function": {
            "name": "query_ledger",
            "description": "Query ledger events.",
            "parameters": {
                "type": "object",
                "properties": {"limit": {"type": "integer"}, "actor_id": {"type": "string"}},
                "required": ["limit"],
            },
        },
    }
    assert out[1]["function"]["name"] == "walk_chain"
    # `input_schema` key is dropped in favor of `parameters`.
    assert "input_schema" not in out[1]["function"]


def test_openai_shim_handles_missing_optional_fields() -> None:
    out = anthropic_tools_to_openai([{"name": "no_desc"}])
    assert out == [{"type": "function", "function": {"name": "no_desc"}}]
    # Empty + nameless are dropped.
    assert anthropic_tools_to_openai([{"description": "x"}]) == []
