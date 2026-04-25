from __future__ import annotations

from collections.abc import AsyncIterator

import pytest

from llm_provider_py.failover import FailoverProvider
from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS


class _P:
    id = "anthropic"

    def chat_complete(
        self, messages: list[ChatMessage], *, temperature: float | None = None, max_output_tokens: int | None = None
    ) -> str:
        return "A"

    async def chat_stream(
        self, messages: list[ChatMessage], *, temperature: float | None = None, max_output_tokens: int | None = None
    ) -> AsyncIterator[str]:
        yield "A"

    def embed(self, text: str) -> list[float]:
        return [0.0]

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


class _O:
    id = "openai"

    def chat_complete(
        self, messages: list[ChatMessage], *, temperature: float | None = None, max_output_tokens: int | None = None
    ) -> str:
        return "B"

    async def chat_stream(
        self, messages: list[ChatMessage], *, temperature: float | None = None, max_output_tokens: int | None = None
    ) -> AsyncIterator[str]:
        yield "B"

    def embed(self, text: str) -> list[float]:
        return [1.0]

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


def test_failover_routes_by_env(monkeypatch: pytest.MonkeyPatch) -> None:
    fo = FailoverProvider(primary=_P(), secondary=_O())  # type: ignore[arg-type]
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "openai")
    assert fo.last_active_id() == "openai"
    assert fo.chat_complete([{"role": "user", "content": "x"}]) == "B"
    monkeypatch.setenv("LLM_PRIMARY_PROVIDER", "anthropic")
    assert fo.last_active_id() == "anthropic"
    assert fo.chat_complete([{"role": "user", "content": "x"}]) == "A"


def test_failover_capability_intersection() -> None:
    class _A(_P):
        id = "a"

        def capabilities(self) -> CapabilityMatrix:
            return {**DEFAULT_CAPS, "embeddings": False}

    class _B(_P):
        id = "b"

    fo = FailoverProvider(primary=_A(), secondary=_B())  # type: ignore[arg-type]
    c = fo.capabilities()
    assert c.get("embeddings") is False
