"""Provider streaming wiring (SSE mocked — no real HTTP)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from llm_provider_py.anthropic import AnthropicProvider
from llm_provider_py.openai import OpenAIProvider


@pytest.mark.asyncio
async def test_anthropic_chat_stream_yields_text(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_iter(self: AnthropicProvider, body: object) -> AsyncIterator[str]:
        yield "a"
        yield "b"

    monkeypatch.setattr(AnthropicProvider, "_iter_sse", fake_iter)  # type: ignore[assignment]
    p = AnthropicProvider(api_key="sk-test")
    out: list[str] = []
    async for c in p.chat_stream([{"role": "user", "content": "x"}]):
        out.append(c)
    assert out == ["a", "b"]


@pytest.mark.asyncio
async def test_openai_chat_stream_yields_text(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_openai(self: OpenAIProvider, body: object) -> AsyncIterator[str]:
        yield "z"

    monkeypatch.setattr(OpenAIProvider, "_openai_sse", fake_openai)  # type: ignore[assignment]
    p = OpenAIProvider(api_key="sk-test")
    out: list[str] = []
    async for c in p.chat_stream([{"role": "user", "content": "y"}]):
        out.append(c)
    assert out == ["z"]
