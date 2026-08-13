"""AnthropicProvider retry policy: 429/5xx/529 + transport errors, backoff, streaming.

The provider's retry contract: retry 429 and 5xx (incl. 529 overloaded_error)
and retryable transport errors with exponential backoff (base 1s, factor 2,
full jitter, 30s cap, Retry-After honored); never retry other 4xx; streaming
retries stop the moment the first SSE chunk reaches the caller. Attempts cap
via constructor ``max_retries`` (wins) or ``DEPLOYAI_LLM_MAX_RETRIES``.
Sleep/rng are constructor-injected so nothing here sleeps for real.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from llm_provider_py.anthropic import AnthropicProvider
from llm_provider_py.types import StopReason, StreamChunk, TextDelta, ToolStreamChunk

_OK_JSON = {
    "content": [{"type": "text", "text": "ok"}],
    "usage": {"input_tokens": 3, "output_tokens": 2},
}

_SSE_EVENTS: list[dict[str, Any]] = [
    {"type": "message_start", "message": {"usage": {"input_tokens": 4, "output_tokens": 0}}},
    {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}},
    {"type": "content_block_delta", "delta": {"type": "text_delta", "text": " world"}},
    {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"input_tokens": 4, "output_tokens": 2}},
]


def _sse_payload(events: list[dict[str, Any]]) -> bytes:
    return b"".join(f"data: {json.dumps(e)}\n".encode() for e in events)


async def _no_sleep(_d: float) -> None:
    return None


# ---------------------------------------------------------------------------
# Non-streaming: status policy + backoff schedule
# ---------------------------------------------------------------------------


def test_chat_complete_retries_429_and_honors_retry_after() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "7"}, text="rate")
        return httpx.Response(200, json=_OK_JSON)

    p = AnthropicProvider(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        _rand=lambda: 0.0,
        _sleep=slept.append,
    )
    assert p.chat_complete([{"role": "user", "content": "x"}]) == "ok"
    assert calls["n"] == 2
    # Jitter drew 0 but Retry-After floors the delay at the server's ask.
    assert slept == [pytest.approx(7.0)]


def test_chat_complete_500_exhausts_max_retries_then_raises() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    p = AnthropicProvider(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        max_retries=3,
        _rand=lambda: 1.0,
        _sleep=slept.append,
    )
    with pytest.raises(OSError, match="Anthropic error 500"):
        p.chat_complete([{"role": "user", "content": "x"}])
    assert calls["n"] == 3
    # rand()=1.0 pins jitter to the exponential ceiling: base 1s, factor 2.
    assert slept == [pytest.approx(1.0), pytest.approx(2.0)]


def test_chat_complete_400_is_never_retried() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(400, text="invalid_request_error")

    p = AnthropicProvider(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        _sleep=slept.append,
    )
    with pytest.raises(OSError, match="Anthropic error 400"):
        p.chat_complete([{"role": "user", "content": "x"}])
    assert calls["n"] == 1
    assert slept == []


def test_chat_complete_transport_error_then_success() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ReadTimeout("read timed out")
        return httpx.Response(200, json=_OK_JSON)

    p = AnthropicProvider(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        _rand=lambda: 0.5,
        _sleep=slept.append,
    )
    assert p.chat_complete([{"role": "user", "content": "x"}]) == "ok"
    assert calls["n"] == 2
    assert slept == [pytest.approx(0.5)]


# ---------------------------------------------------------------------------
# Streaming: retry until the first chunk, never after
# ---------------------------------------------------------------------------


async def _collect_stream(p: AnthropicProvider) -> list[StreamChunk]:
    out: list[StreamChunk] = []
    async for c in p.chat_complete_stream([{"role": "user", "content": "x"}]):
        out.append(c)
    await p.aclose()
    return out


@pytest.mark.asyncio
async def test_stream_retries_connection_phase_529_then_delivers_full_stream() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    async def rec_sleep(d: float) -> None:
        slept.append(d)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(529, text='{"type": "error", "error": {"type": "overloaded_error"}}')
        return httpx.Response(200, content=_sse_payload(_SSE_EVENTS))

    p = AnthropicProvider(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        _rand=lambda: 0.0,
        _async_sleep=rec_sleep,
    )
    out = await _collect_stream(p)
    assert calls["n"] == 2
    assert len(slept) == 1
    assert [c.delta for c in out if not c.done] == ["Hello", " world"]
    assert out[-1].done and out[-1].tokens_used == 6


@pytest.mark.asyncio
async def test_stream_retries_transport_error_before_first_chunk() -> None:
    calls = {"n": 0}

    async def dead_body() -> AsyncIterator[bytes]:
        raise httpx.ReadError("connection reset before first byte")
        yield b""  # unreachable — makes this an async generator

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(200, content=dead_body())
        return httpx.Response(200, content=_sse_payload(_SSE_EVENTS))

    p = AnthropicProvider(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        _rand=lambda: 0.0,
        _async_sleep=_no_sleep,
    )
    out = await _collect_stream(p)
    assert calls["n"] == 2
    assert [c.delta for c in out if not c.done] == ["Hello", " world"]


@pytest.mark.asyncio
async def test_stream_disconnect_after_first_chunk_surfaces_without_retry() -> None:
    calls = {"n": 0}

    async def broken_body() -> AsyncIterator[bytes]:
        yield _sse_payload(_SSE_EVENTS[:2])
        raise httpx.ReadError("mid-stream disconnect")

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=broken_body())

    p = AnthropicProvider(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        _async_sleep=_no_sleep,
    )
    got: list[str] = []
    with pytest.raises(httpx.ReadError, match="mid-stream disconnect"):
        async for c in p.chat_complete_stream([{"role": "user", "content": "x"}]):
            if not c.done:
                got.append(c.delta)
    await p.aclose()
    # The chunk before the disconnect reached the caller; no replay happened.
    assert got == ["Hello"]
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_stream_with_tools_retries_529_then_delivers() -> None:
    calls = {"n": 0}
    events: list[dict[str, Any]] = [
        {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "done"}},
        {"type": "message_delta", "delta": {"stop_reason": "end_turn"}, "usage": {"output_tokens": 1}},
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(529, text="overloaded")
        return httpx.Response(200, content=_sse_payload(events))

    p = AnthropicProvider(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        _rand=lambda: 0.0,
        _async_sleep=_no_sleep,
    )
    out: list[ToolStreamChunk] = []
    async for c in p.chat_complete_stream_with_tools([{"role": "user", "content": "x"}], []):
        out.append(c)
    await p.aclose()
    assert calls["n"] == 2
    assert [c.content for c in out if isinstance(c, TextDelta)] == ["done"]
    assert isinstance(out[-1], StopReason)


# ---------------------------------------------------------------------------
# max_retries resolution: constructor > env > default
# ---------------------------------------------------------------------------


def _count_500s(p: AnthropicProvider, calls: dict[str, int]) -> int:
    with pytest.raises(OSError, match="Anthropic error 500"):
        p.chat_complete([{"role": "user", "content": "x"}])
    return calls["n"]


def _always_500(calls: dict[str, int]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(500, text="boom")

    return httpx.MockTransport(handler)


def test_max_retries_resolves_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_LLM_MAX_RETRIES", "2")
    calls = {"n": 0}
    p = AnthropicProvider(api_key="sk-test", transport=_always_500(calls), _rand=lambda: 0.0, _sleep=lambda _d: None)
    assert _count_500s(p, calls) == 2


def test_max_retries_constructor_beats_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_LLM_MAX_RETRIES", "1")
    calls = {"n": 0}
    p = AnthropicProvider(
        api_key="sk-test",
        transport=_always_500(calls),
        max_retries=3,
        _rand=lambda: 0.0,
        _sleep=lambda _d: None,
    )
    assert _count_500s(p, calls) == 3


@pytest.mark.parametrize("raw", ["", "junk"])
def test_max_retries_env_unset_or_invalid_uses_default(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    if raw:
        monkeypatch.setenv("DEPLOYAI_LLM_MAX_RETRIES", raw)
    else:
        monkeypatch.delenv("DEPLOYAI_LLM_MAX_RETRIES", raising=False)
    calls = {"n": 0}
    p = AnthropicProvider(api_key="sk-test", transport=_always_500(calls), _rand=lambda: 0.0, _sleep=lambda _d: None)
    # Package default: 3 attempts (up to 2 retries).
    assert _count_500s(p, calls) == 3
