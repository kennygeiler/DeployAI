"""Extended-thinking support in AnthropicProvider.chat_complete_stream_with_tools.

Covers the request-body contract (the ``thinking`` param appears only when
a budget is enabled, ``max_tokens`` always exceeds the budget, temperature
is dropped) and the stream contract (``thinking_delta`` SSE events surface
as :class:`ThinkingDelta` chunks without disturbing text / tool-use).
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from llm_provider_py.anthropic import AnthropicProvider
from llm_provider_py.types import (
    StopReason,
    TextDelta,
    ThinkingDelta,
    ThinkingSignature,
    ToolStreamChunk,
    ToolUseEnd,
)

_TOOL_SPEC: list[dict[str, Any]] = [
    {
        "name": "query_ledger",
        "description": "Query the ledger.",
        "input_schema": {"type": "object", "properties": {}, "required": []},
    }
]

_THINKING_EVENTS: list[dict[str, Any]] = [
    {"type": "message_start", "message": {"usage": {"input_tokens": 10, "output_tokens": 0}}},
    {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Check the "}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "open risks."}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "sig=="}},
    {"type": "content_block_stop", "index": 0},
    {"type": "content_block_start", "index": 1, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 1, "delta": {"type": "text_delta", "text": "Two risks remain."}},
    {"type": "content_block_stop", "index": 1},
    {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 40}},
]


def _sse_payload(events: list[dict[str, Any]]) -> bytes:
    return b"".join(f"data: {json.dumps(e)}\n".encode() for e in events)


def _mock_provider(
    captured: dict[str, Any],
    *,
    events: list[dict[str, Any]],
    **provider_kwargs: Any,
) -> AnthropicProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, content=_sse_payload(events))

    return AnthropicProvider(api_key="sk-test", transport=httpx.MockTransport(handler), **provider_kwargs)


async def _collect(
    provider: AnthropicProvider,
    *,
    temperature: float = 0.1,
    max_output_tokens: int = 800,
) -> list[ToolStreamChunk]:
    out: list[ToolStreamChunk] = []
    async for c in provider.chat_complete_stream_with_tools(
        [{"role": "user", "content": "state?"}],
        _TOOL_SPEC,
        temperature=temperature,
        max_output_tokens=max_output_tokens,
    ):
        out.append(c)
    await provider.aclose()
    return out


@pytest.mark.asyncio
async def test_thinking_enabled_sends_param_and_yields_thinking_deltas() -> None:
    captured: dict[str, Any] = {}
    p = _mock_provider(captured, events=_THINKING_EVENTS, thinking_budget_tokens=2048)
    out = await _collect(p)

    body = captured["body"]
    # Default model is 5-family: budget_tokens was removed there (400), the
    # on-shape is adaptive. The budget still sizes the max_tokens headroom.
    assert body["thinking"] == {"type": "adaptive"}
    # Thinking spends from max_tokens: 800 <= 2048 → grown to 2048 + 800.
    assert body["max_tokens"] == 2848
    # thinking is incompatible with a pinned temperature.
    assert "temperature" not in body

    thinking = [c for c in out if isinstance(c, ThinkingDelta)]
    assert [c.content for c in thinking] == ["Check the ", "open risks."]
    # The thinking block's close surfaces its signature (from signature_delta)
    # so callers can replay the block on the follow-up request.
    sigs = [c for c in out if isinstance(c, ThinkingSignature)]
    assert [c.signature for c in sigs] == ["sig=="]
    # Boundary ordering: signature arrives after the block's deltas and
    # before the text that follows it.
    assert out.index(sigs[0]) > out.index(thinking[-1])
    text = [c for c in out if isinstance(c, TextDelta)]
    assert [c.content for c in text] == ["Two risks remain."]
    assert out.index(sigs[0]) < out.index(text[0])
    assert isinstance(out[-1], StopReason)
    assert out[-1].reason == "end_turn"


@pytest.mark.asyncio
async def test_thinking_disabled_omits_param_and_drops_nothing_else() -> None:
    captured: dict[str, Any] = {}
    # model pinned pre-5 so a temperature would normally be sent.
    p = _mock_provider(captured, events=_THINKING_EVENTS, model="claude-opus-4-1")
    out = await _collect(p)

    body = captured["body"]
    assert "thinking" not in body
    assert body["max_tokens"] == 800
    assert body["temperature"] == 0.1
    # A rogue thinking_delta without the request param still parses safely.
    assert [c.content for c in out if isinstance(c, ThinkingDelta)] == ["Check the ", "open risks."]
    assert [c.content for c in out if isinstance(c, TextDelta)] == ["Two risks remain."]


@pytest.mark.asyncio
async def test_thinking_budget_resolves_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_ANTHROPIC_THINKING_BUDGET", "1024")
    captured: dict[str, Any] = {}
    p = _mock_provider(captured, events=_THINKING_EVENTS)
    await _collect(p)
    assert captured["body"]["thinking"] == {"type": "adaptive"}
    assert captured["body"]["max_tokens"] == 1024 + 800


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["", "0", "-5", "lots"])
async def test_thinking_env_zero_unset_or_invalid_disables(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    if raw:
        monkeypatch.setenv("DEPLOYAI_ANTHROPIC_THINKING_BUDGET", raw)
    else:
        monkeypatch.delenv("DEPLOYAI_ANTHROPIC_THINKING_BUDGET", raising=False)
    captured: dict[str, Any] = {}
    p = _mock_provider(captured, events=_THINKING_EVENTS)
    await _collect(p)
    # Default model is a 5-family model: thinking-off must be sent as an
    # explicit disable, because omission means adaptive-on there.
    assert captured["body"]["thinking"] == {"type": "disabled"}


@pytest.mark.asyncio
async def test_thinking_max_tokens_kept_when_already_above_budget() -> None:
    captured: dict[str, Any] = {}
    p = _mock_provider(captured, events=_THINKING_EVENTS, thinking_budget_tokens=512)
    await _collect(p, max_output_tokens=4096)
    assert captured["body"]["thinking"] == {"type": "adaptive"}
    assert captured["body"]["max_tokens"] == 4096


@pytest.mark.asyncio
async def test_thinking_enabled_pre5_model_keeps_budget_tokens_shape() -> None:
    captured: dict[str, Any] = {}
    p = _mock_provider(captured, events=_THINKING_EVENTS, model="claude-opus-4-1", thinking_budget_tokens=2048)
    await _collect(p)
    body = captured["body"]
    assert body["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert body["max_tokens"] == 2848
    # Pre-5 models normally take a temperature; thinking-on must drop it.
    assert "temperature" not in body


@pytest.mark.asyncio
async def test_thinking_budget_on_fable_omits_thinking_param_entirely() -> None:
    # claude-fable-5 / claude-mythos-5 reject ANY explicit thinking config —
    # a configured budget must not produce a thinking param (only headroom).
    captured: dict[str, Any] = {}
    p = _mock_provider(captured, events=_THINKING_EVENTS, model="claude-fable-5", thinking_budget_tokens=2048)
    await _collect(p)
    body = captured["body"]
    assert "thinking" not in body
    assert body["max_tokens"] == 2848
    assert "temperature" not in body


@pytest.mark.asyncio
async def test_signature_accumulates_across_deltas_and_pairs_with_tool_use() -> None:
    """Multi-part signature_delta events concatenate; tool_use blocks after a
    thinking block still close normally (thinking + tool_use share the stream)."""
    events: list[dict[str, Any]] = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 10, "output_tokens": 0}}},
        {"type": "content_block_start", "index": 0, "content_block": {"type": "thinking", "thinking": ""}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "Need ledger."}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "abc"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "def=="}},
        {"type": "content_block_stop", "index": 0},
        {
            "type": "content_block_start",
            "index": 1,
            "content_block": {"type": "tool_use", "id": "toolu_1", "name": "query_ledger"},
        },
        {"type": "content_block_delta", "index": 1, "delta": {"type": "input_json_delta", "partial_json": "{}"}},
        {"type": "content_block_stop", "index": 1},
        {"type": "message_delta", "delta": {"stop_reason": "tool_use"}, "usage": {"output_tokens": 20}},
    ]
    captured: dict[str, Any] = {}
    p = _mock_provider(captured, events=events, thinking_budget_tokens=1024)
    out = await _collect(p)

    sigs = [c for c in out if isinstance(c, ThinkingSignature)]
    assert [c.signature for c in sigs] == ["abcdef=="]
    ends = [c for c in out if isinstance(c, ToolUseEnd)]
    assert [c.id for c in ends] == ["toolu_1"]
    # The thinking block's stop must not be mistaken for the tool_use stop.
    assert out.index(sigs[0]) < out.index(ends[0])
    assert isinstance(out[-1], StopReason)
    assert out[-1].reason == "tool_use"


@pytest.mark.asyncio
async def test_thinking_delta_without_block_start_still_yields_signature() -> None:
    """A stream missing content_block_start for the thinking block (defensive)
    still tracks the block via its deltas and surfaces the signature."""
    events: list[dict[str, Any]] = [
        {"type": "content_block_delta", "index": 0, "delta": {"type": "thinking_delta", "thinking": "hm"}},
        {"type": "content_block_delta", "index": 0, "delta": {"type": "signature_delta", "signature": "s=="}},
        {"type": "content_block_stop", "index": 0},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 5}},
    ]
    captured: dict[str, Any] = {}
    p = _mock_provider(captured, events=events, thinking_budget_tokens=1024)
    out = await _collect(p)
    assert [c.signature for c in out if isinstance(c, ThinkingSignature)] == ["s=="]


@pytest.mark.asyncio
async def test_method_budget_override_beats_constructor() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(200, content=_sse_payload(_THINKING_EVENTS))

    p = AnthropicProvider(api_key="sk-test", transport=httpx.MockTransport(handler), thinking_budget_tokens=2048)
    out: list[ToolStreamChunk] = []
    async for c in p.chat_complete_stream_with_tools(
        [{"role": "user", "content": "x"}],
        _TOOL_SPEC,
        max_output_tokens=800,
        thinking_budget_tokens=0,
    ):
        out.append(c)
    await p.aclose()
    # Per-call budget 0 on the default (5-family) model → explicit disable.
    assert captured["body"]["thinking"] == {"type": "disabled"}
    assert captured["body"]["max_tokens"] == 800


# --- 5-family default-on thinking (Wave 3 K4 demo-reliability fix) ---------
#
# Claude Sonnet 5 / Opus 5 run adaptive thinking when the `thinking` param is
# omitted, and max_tokens caps thinking + text together — the Cartographer
# extractor's 2000-token budget was burned entirely by thinking, returning
# zero text. The provider must pin its thinking-off contract explicitly.


def _capture_sync(captured: dict[str, Any], *, model: str) -> AnthropicProvider:
    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content.decode())
        return httpx.Response(
            200,
            json={"content": [{"type": "text", "text": "[]"}], "usage": {}},
        )

    return AnthropicProvider(api_key="sk-test", transport=httpx.MockTransport(handler), model=model)


@pytest.mark.parametrize("model", ["claude-sonnet-5", "claude-opus-5"])
def test_chat_complete_disables_thinking_on_5_family(model: str) -> None:
    captured: dict[str, Any] = {}
    p = _capture_sync(captured, model=model)
    assert p.chat_complete([{"role": "user", "content": "extract"}], max_output_tokens=2000) == "[]"
    assert captured["body"]["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize("model", ["claude-opus-4-1", "claude-sonnet-4-5", "claude-fable-5"])
def test_chat_complete_omits_thinking_elsewhere(model: str) -> None:
    """Pre-5 models: omission already means no thinking. claude-fable-5:
    thinking is always-on and an explicit disable is REJECTED — must omit."""
    captured: dict[str, Any] = {}
    p = _capture_sync(captured, model=model)
    p.chat_complete([{"role": "user", "content": "extract"}])
    assert "thinking" not in captured["body"]
