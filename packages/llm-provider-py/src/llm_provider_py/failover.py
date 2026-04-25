"""Primary/secondary provider routing (Epic 5, Story 5.2, NFR70)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

from llm_provider_py.types import CapabilityMatrix, ChatMessage, LLMProvider


def _primary_name() -> str:
    return (os.environ.get("LLM_PRIMARY_PROVIDER") or "anthropic").strip().lower()


class FailoverProvider:
    """Routes to ``primary`` when ``LLM_PRIMARY_PROVIDER`` matches its id, else ``secondary``."""

    def __init__(self, *, primary: LLMProvider, secondary: LLMProvider) -> None:
        self._a = primary
        self._b = secondary
        self.id = "failover"

    def _active(self) -> LLMProvider:
        want = _primary_name()
        if want == self._a.id:
            return self._a
        if want == self._b.id:
            return self._b
        return self._a

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        p = self._active()
        return p.chat_complete(
            messages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        )

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        p = self._active()
        async for chunk in p.chat_stream(
            messages,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
        ):
            yield chunk

    def embed(self, text: str) -> list[float]:
        return self._active().embed(text)

    def capabilities(self) -> CapabilityMatrix:
        # Intersection: both must support a key for failover safety
        ca = self._a.capabilities()
        cb = self._b.capabilities()
        return {k: bool(ca.get(k) and cb.get(k)) for k in set(ca) | set(cb)}

    def last_active_id(self) -> str:
        return self._active().id


def create_failover_from_env() -> FailoverProvider:
    from llm_provider_py.anthropic import AnthropicProvider
    from llm_provider_py.openai import OpenAIProvider

    return FailoverProvider(primary=AnthropicProvider(), secondary=OpenAIProvider())
