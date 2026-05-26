"""Streaming contract: StreamChunk iterator across stub + Anthropic providers."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

import pytest

from llm_provider_py.anthropic import AnthropicProvider
from llm_provider_py.openai import OpenAIProvider
from llm_provider_py.stub import create_stub_provider
from llm_provider_py.types import StreamChunk


@pytest.mark.asyncio
async def test_stub_chat_complete_stream_yields_chunks_then_done() -> None:
    p = create_stub_provider()
    chunks: list[StreamChunk] = []
    async for c in p.chat_complete_stream([{"role": "user", "content": "hi"}]):
        chunks.append(c)
    assert len(chunks) >= 4  # at least 3 deltas + final done
    body_chunks = chunks[:-1]
    final = chunks[-1]
    assert len(body_chunks) >= 3
    assert all(isinstance(c, StreamChunk) for c in chunks)
    assert all(not c.done for c in body_chunks)
    assert all(c.delta for c in body_chunks)
    assert final.done is True
    assert final.delta == ""
    assert final.tokens_used > 0
    joined = "".join(c.delta for c in body_chunks)
    assert "stub" in joined and "stream" in joined


@pytest.mark.asyncio
async def test_stub_stream_cleanly_exhausts_on_early_break() -> None:
    p = create_stub_provider()
    it = p.chat_complete_stream([{"role": "user", "content": "hi"}])
    first = await it.__anext__()
    assert isinstance(first, StreamChunk)
    await it.aclose()


def _encode_sse(events: list[dict[str, Any]]) -> list[bytes]:
    return [f"data: {json.dumps(e)}\n".encode() for e in events]


@pytest.mark.asyncio
async def test_anthropic_chat_complete_stream_mocked(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}
    events = [
        {"type": "message_start", "message": {"usage": {"input_tokens": 7, "output_tokens": 0}}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": " world"}},
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "!"}},
        {"type": "message_delta", "usage": {"input_tokens": 7, "output_tokens": 5}},
    ]

    async def fake_iter_events(self: AnthropicProvider, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        captured["body"] = body
        for ev in events:
            yield ev

    monkeypatch.setattr(AnthropicProvider, "_iter_sse_events", fake_iter_events)  # type: ignore[assignment]

    p = AnthropicProvider(api_key="sk-test")
    out: list[StreamChunk] = []
    async for c in p.chat_complete_stream(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        temperature=0.3,
        max_output_tokens=64,
    ):
        out.append(c)

    body = captured["body"]
    assert body["stream"] is True
    assert body["max_tokens"] == 64
    assert body["temperature"] == 0.3
    assert body["system"] == "sys"
    assert body["messages"] == [{"role": "user", "content": "hi"}]

    deltas = [c.delta for c in out if not c.done]
    assert deltas == ["Hello", " world", "!"]
    final = out[-1]
    assert final.done is True
    assert final.delta == ""
    assert final.tokens_used == 12


@pytest.mark.asyncio
async def test_anthropic_chat_complete_stream_handles_sse_bytes(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end SSE byte parsing via _iter_sse_events."""
    events = [
        {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}},
        {"type": "message_delta", "usage": {"input_tokens": 3, "output_tokens": 1}},
    ]
    payload_lines = _encode_sse(events)

    class _FakeResp:
        status_code = 200

        async def aiter_bytes(self) -> AsyncIterator[bytes]:
            for chunk in payload_lines:
                yield chunk

        async def aread(self) -> bytes:
            return b""

    class _StreamCtx:
        async def __aenter__(self) -> _FakeResp:
            return _FakeResp()

        async def __aexit__(self, *a: object) -> None:
            return None

    class _FakeClient:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> _FakeClient:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        def stream(self, *a: object, **k: object) -> _StreamCtx:
            return _StreamCtx()

    import httpx as hx

    monkeypatch.setattr(hx, "AsyncClient", _FakeClient)

    p = AnthropicProvider(api_key="sk-test")
    out: list[StreamChunk] = []
    async for c in p.chat_complete_stream([{"role": "user", "content": "x"}]):
        out.append(c)
    assert [c.delta for c in out if not c.done] == ["ok"]
    final = out[-1]
    assert final.done is True
    assert final.tokens_used == 4


@pytest.mark.asyncio
async def test_anthropic_stream_early_break_releases_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    """Early break on the outer iterator must not leave the inner SSE source pumping."""
    events_yielded: list[str] = []
    inner_handle: dict[str, Any] = {}

    async def fake_iter_events(self: AnthropicProvider, body: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
        try:
            for txt in ("a", "b", "c", "d"):
                events_yielded.append(txt)
                yield {"type": "content_block_delta", "delta": {"type": "text_delta", "text": txt}}
        except GeneratorExit:
            inner_handle["closed_via_exit"] = True
            raise

    monkeypatch.setattr(AnthropicProvider, "_iter_sse_events", fake_iter_events)  # type: ignore[assignment]
    p = AnthropicProvider(api_key="sk-test")

    it = p.chat_complete_stream([{"role": "user", "content": "x"}])
    first = await it.__anext__()
    assert first.delta == "a"
    await it.aclose()
    # outer is closed; inner SSE stopped producing more events
    assert events_yielded == ["a"]
    # outer aclose must not raise nor leak pending coroutines
    with pytest.raises(StopAsyncIteration):
        await it.__anext__()


@pytest.mark.asyncio
async def test_openai_chat_complete_stream_raises_not_implemented() -> None:
    p = OpenAIProvider(api_key="sk-test")
    # Method is an async generator: error surfaces on first iteration, not on
    # call. Caller's `async for chunk in provider.chat_complete_stream(...)`
    # contract preserved.
    it = p.chat_complete_stream([{"role": "user", "content": "x"}])
    with pytest.raises(NotImplementedError):
        await it.__anext__()


def test_chat_complete_backward_compat_signature() -> None:
    """Existing sync chat_complete callers unaffected by new streaming method."""
    p = create_stub_provider()
    out = p.chat_complete([{"role": "user", "content": "abc"}])
    assert isinstance(out, str)
    assert out.startswith("stub:")
