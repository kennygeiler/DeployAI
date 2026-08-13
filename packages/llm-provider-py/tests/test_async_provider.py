"""Async provider path (ticket D0): chat_complete_async, backoff policy, stream-open retries."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from llm_provider_py.anthropic import AnthropicProvider
from llm_provider_py.failover import FailoverProvider
from llm_provider_py.openai import OpenAIProvider
from llm_provider_py.stub import create_stub_provider
from llm_provider_py.types import StreamChunk
from llm_provider_py.util import (
    compute_backoff_delay,
    httpx_post_with_retries,
    httpx_post_with_retries_async,
    parse_retry_after,
)

_ANTHROPIC_OK = {
    "content": [{"type": "text", "text": "hello from claude"}],
    "usage": {"input_tokens": 5, "output_tokens": 2},
}
_OPENAI_OK = {
    "choices": [{"message": {"content": "hello from gpt"}}],
    "usage": {"prompt_tokens": 5, "completion_tokens": 2},
}


# ---------------------------------------------------------------------------
# Pure backoff computation
# ---------------------------------------------------------------------------


def test_backoff_full_jitter_bounds() -> None:
    # rand()=1.0 hits the exponential ceiling; rand()=0.0 hits zero.
    assert compute_backoff_delay(0, base_delay_s=0.15, rand=lambda: 1.0) == pytest.approx(0.15)
    assert compute_backoff_delay(2, base_delay_s=0.15, rand=lambda: 1.0) == pytest.approx(0.6)
    assert compute_backoff_delay(2, base_delay_s=0.15, rand=lambda: 0.0) == 0.0
    # Any rand value stays within [0, ceiling].
    for r in (0.1, 0.5, 0.99):
        d = compute_backoff_delay(3, base_delay_s=0.15, rand=lambda r=r: r)
        assert 0.0 <= d <= 0.15 * 8


def test_backoff_retry_after_is_a_floor() -> None:
    # Server asked for 3s; jitter would have picked something smaller.
    d = compute_backoff_delay(0, base_delay_s=0.15, retry_after_s=3.0, rand=lambda: 0.0)
    assert d == pytest.approx(3.0)
    # If jitter picks a larger delay than Retry-After, jitter wins.
    d = compute_backoff_delay(10, base_delay_s=0.15, max_delay_s=30.0, retry_after_s=3.0, rand=lambda: 1.0)
    assert d == pytest.approx(30.0)


def test_backoff_max_delay_caps_everything() -> None:
    # A huge attempt count and a hostile Retry-After both cap at max_delay_s.
    assert compute_backoff_delay(30, max_delay_s=5.0, rand=lambda: 1.0) == pytest.approx(5.0)
    assert compute_backoff_delay(0, max_delay_s=5.0, retry_after_s=600.0, rand=lambda: 0.0) == pytest.approx(5.0)


def test_parse_retry_after_seconds_and_http_date() -> None:
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("3") == pytest.approx(3.0)
    assert parse_retry_after("0.5") == pytest.approx(0.5)
    assert parse_retry_after("garbage") is None
    # HTTP-date form: 10s in the future relative to the injected clock.
    # (Fri, 31 Dec 1999 23:59:59 GMT == epoch 946684799)
    got = parse_retry_after("Fri, 31 Dec 1999 23:59:59 GMT", now=lambda: 946684799.0 - 10.0)
    assert got == pytest.approx(10.0)
    # A date in the past clamps to zero, never negative.
    got = parse_retry_after("Fri, 31 Dec 1999 23:59:59 GMT", now=lambda: 946684799.0 + 60.0)
    assert got == 0.0


# ---------------------------------------------------------------------------
# Sync helper: Retry-After + jitter now honored
# ---------------------------------------------------------------------------


def test_sync_retries_honor_retry_after() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "2"}, text="rate")
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        r = httpx_post_with_retries(
            client,
            "https://example.com/x",
            headers={},
            json={},
            rand=lambda: 0.0,
            sleep=slept.append,
        )
    assert r.status_code == 200
    assert calls["n"] == 2
    assert slept == [pytest.approx(2.0)]


# ---------------------------------------------------------------------------
# Async helper
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_async_retries_429_with_retry_after_honored() -> None:
    calls = {"n": 0}
    slept: list[float] = []

    async def fake_sleep(d: float) -> None:
        slept.append(d)

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "3"}, text="rate")
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        r = await httpx_post_with_retries_async(
            client,
            "https://example.com/x",
            headers={},
            json={},
            rand=lambda: 0.0,
            sleep=fake_sleep,
        )
    assert r.status_code == 200
    assert calls["n"] == 2
    assert slept == [pytest.approx(3.0)]


@pytest.mark.asyncio
async def test_async_retries_connect_error_then_success() -> None:
    calls = {"n": 0}

    async def fake_sleep(d: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            raise httpx.ConnectError("refused")
        return httpx.Response(200, json={"ok": True})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        r = await httpx_post_with_retries_async(
            client,
            "https://example.com/x",
            headers={},
            json={},
            sleep=fake_sleep,
        )
    assert r.status_code == 200
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_async_gives_up_when_elapsed_budget_cannot_fit_delay() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        # Retry-After far larger than the elapsed budget: no sleep possible.
        return httpx.Response(429, headers={"retry-after": "100"}, text="rate")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        r = await httpx_post_with_retries_async(
            client,
            "https://example.com/x",
            headers={},
            json={},
            max_elapsed_s=1.0,
        )
    assert r.status_code == 429
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_async_connect_error_exhaustion_reraises() -> None:
    calls = {"n": 0}

    async def fake_sleep(d: float) -> None:
        return None

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        raise httpx.ConnectError("refused")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.ConnectError):
            await httpx_post_with_retries_async(
                client,
                "https://example.com/x",
                headers={},
                json={},
                max_retries=3,
                sleep=fake_sleep,
            )
    assert calls["n"] == 3


# ---------------------------------------------------------------------------
# chat_complete_async on the concrete providers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anthropic_chat_complete_async_happy_path() -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["body"] = request.read()
        return httpx.Response(200, json=_ANTHROPIC_OK)

    usage_events: list[dict[str, Any]] = []
    p = AnthropicProvider(
        api_key="sk-test",
        transport=httpx.MockTransport(handler),
        on_usage=usage_events.append,
    )
    out = await p.chat_complete_async(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        temperature=0.1,
        max_output_tokens=64,
    )
    await p.aclose()
    assert out == "hello from claude"
    assert "api.anthropic.com" in seen["url"]
    assert usage_events and usage_events[0]["usage"] == {"input_tokens": 5, "output_tokens": 2}


@pytest.mark.asyncio
async def test_anthropic_chat_complete_async_shares_one_client() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ANTHROPIC_OK)

    p = AnthropicProvider(api_key="sk-test", transport=httpx.MockTransport(handler))
    c1 = p._get_async_client()
    await p.chat_complete_async([{"role": "user", "content": "a"}])
    await p.chat_complete_async([{"role": "user", "content": "b"}])
    assert p._get_async_client() is c1
    await p.aclose()
    assert c1.is_closed
    # aclose is idempotent.
    await p.aclose()


@pytest.mark.asyncio
async def test_openai_chat_complete_async_happy_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_OPENAI_OK)

    p = OpenAIProvider(api_key="sk-test", transport=httpx.MockTransport(handler))
    out = await p.chat_complete_async([{"role": "user", "content": "hi"}])
    await p.aclose()
    assert out == "hello from gpt"


@pytest.mark.asyncio
async def test_stub_and_failover_expose_chat_complete_async() -> None:
    stub = create_stub_provider()
    out = await stub.chat_complete_async([{"role": "user", "content": "abc"}])
    assert out == "stub:abc"

    fo = FailoverProvider(primary=create_stub_provider(), secondary=create_stub_provider())
    out = await fo.chat_complete_async([{"role": "user", "content": "xyz"}])
    assert out == "stub:xyz"


@pytest.mark.asyncio
async def test_anthropic_chat_complete_async_retries_429_then_ok() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, text="rate")
        return httpx.Response(200, json=_ANTHROPIC_OK)

    p = AnthropicProvider(api_key="sk-test", transport=httpx.MockTransport(handler), _rand=lambda: 0.0)
    out = await p.chat_complete_async([{"role": "user", "content": "hi"}])
    await p.aclose()
    assert out == "hello from claude"
    assert calls["n"] == 2


# ---------------------------------------------------------------------------
# Streaming: initial-connection retry, but never mid-stream
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stream_retries_initial_connection_on_429() -> None:
    calls = {"n": 0}
    sse = b'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "ok"}}\n'

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(429, headers={"retry-after": "0"}, text="rate")
        return httpx.Response(200, content=sse)

    p = AnthropicProvider(api_key="sk-test", transport=httpx.MockTransport(handler), _rand=lambda: 0.0)
    out: list[StreamChunk] = []
    async for c in p.chat_complete_stream([{"role": "user", "content": "x"}]):
        out.append(c)
    await p.aclose()
    assert calls["n"] == 2
    assert [c.delta for c in out if not c.done] == ["ok"]


@pytest.mark.asyncio
async def test_stream_does_not_retry_after_bytes_were_yielded() -> None:
    """A mid-stream failure must propagate, not silently re-issue the request."""
    calls = {"n": 0}

    async def broken_body() -> AsyncIterator[bytes]:
        yield b'data: {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "partial"}}\n'
        raise RuntimeError("mid-stream failure")

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, content=broken_body())

    p = AnthropicProvider(api_key="sk-test", transport=httpx.MockTransport(handler))
    got: list[str] = []
    with pytest.raises(RuntimeError, match="mid-stream failure"):
        async for c in p.chat_complete_stream([{"role": "user", "content": "x"}]):
            if not c.done:
                got.append(c.delta)
    await p.aclose()
    # The first delta reached the caller, and no second request was made.
    assert got == ["partial"]
    assert calls["n"] == 1


# ---------------------------------------------------------------------------
# Event-loop non-blocking smoke
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_complete_async_does_not_starve_the_event_loop() -> None:
    """A slow provider response must not block concurrently scheduled tasks.

    The MockTransport handler awaits 0.2s (simulated network latency).
    A ticker task increments every 10ms; if the loop were blocked the way
    the sync client blocks it, the ticker would barely advance.
    """

    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return httpx.Response(200, json=_ANTHROPIC_OK)

    ticks = 0
    stop = asyncio.Event()

    async def ticker() -> None:
        nonlocal ticks
        while not stop.is_set():
            await asyncio.sleep(0.01)
            ticks += 1

    task = asyncio.create_task(ticker())
    try:
        p = AnthropicProvider(api_key="sk-test", transport=httpx.MockTransport(handler))
        out = await p.chat_complete_async([{"role": "user", "content": "hi"}])
        await p.aclose()
    finally:
        stop.set()
        await task
    assert out == "hello from claude"
    # Generous lower bound: ~20 ticks expected during the 0.2s wait.
    assert ticks >= 5
