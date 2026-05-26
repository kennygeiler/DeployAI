from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from llm_provider_py.types import CapabilityMatrix, ChatMessage, StreamChunk
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed

STUB_STREAM_REPLY = "stub streaming reply for tests"


def create_stub_provider() -> Any:
    """All capabilities True — matrix validation and tests."""

    class _Stub:
        id = "stub"

        def chat_complete(
            self,
            messages: list[ChatMessage],
            *,
            temperature: float | None = None,
            max_output_tokens: int | None = None,
        ) -> str:
            _ = temperature, max_output_tokens
            last = [m for m in messages if m.get("role") != "system"][-1] if messages else {"content": ""}
            c = str(last.get("content", ""))
            return f"stub:{c[:12]}"

        async def chat_stream(
            self,
            messages: list[ChatMessage],
            *,
            temperature: float | None = None,
            max_output_tokens: int | None = None,
        ) -> AsyncIterator[str]:
            s = self.chat_complete(
                messages,
                temperature=temperature,
                max_output_tokens=max_output_tokens,
            )
            for i in range(0, len(s), 3):
                yield s[i : i + 3]

        async def chat_complete_stream(
            self,
            messages: list[ChatMessage],
            *,
            temperature: float = 0.2,
            max_output_tokens: int = 1024,
        ) -> AsyncIterator[StreamChunk]:
            _ = messages, temperature, max_output_tokens
            words = STUB_STREAM_REPLY.split(" ")
            for idx, word in enumerate(words):
                delta = word if idx == 0 else " " + word
                yield StreamChunk(delta=delta, done=False, tokens_used=0)
            yield StreamChunk(delta="", done=True, tokens_used=len(words))

        def embed(self, text: str) -> list[float]:
            return pseudo_embed(text, 16)

        def capabilities(self) -> CapabilityMatrix:
            return {**DEFAULT_CAPS}

    return _Stub()
