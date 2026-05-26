from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

CapabilityMatrix = dict[str, bool]

ChatMessage = dict[str, str]  # role: system|user|assistant, content


@dataclass(frozen=True)
class StreamChunk:
    delta: str
    done: bool
    tokens_used: int


@runtime_checkable
class LLMProvider(Protocol):
    id: str

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str: ...

    def embed(self, text: str) -> list[float]: ...

    def capabilities(self) -> CapabilityMatrix: ...

    def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]: ...

    def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]: ...
