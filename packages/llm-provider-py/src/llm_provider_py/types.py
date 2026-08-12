from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

CapabilityMatrix = dict[str, bool]

ChatMessage = dict[str, Any]  # role: system|user|assistant, content: str | list[block]


@dataclass(frozen=True)
class StreamChunk:
    delta: str
    done: bool
    tokens_used: int


@dataclass(frozen=True)
class TextDelta:
    """Plain text streamed alongside (or instead of) tool_use blocks."""

    content: str


@dataclass(frozen=True)
class ThinkingDelta:
    """Streamed extended-thinking text (Anthropic ``thinking_delta``).

    Emitted by providers only when a thinking budget is enabled; consumers
    that do not handle it can ignore it without affecting the text /
    tool-use protocol.
    """

    content: str


@dataclass(frozen=True)
class ThinkingSignature:
    """The thinking block closed; ``signature`` is its integrity signature.

    The Anthropic API requires that when thinking is enabled and an
    assistant turn contains tool_use blocks, the replayed assistant message
    on the follow-up request starts with the original thinking block
    including this signature. Consumers that never replay thinking turns
    can ignore it, like :class:`ThinkingDelta`.
    """

    signature: str


@dataclass(frozen=True)
class ToolUseStart:
    """Marker that a new tool_use content block has begun."""

    id: str
    name: str


@dataclass(frozen=True)
class ToolUseInputDelta:
    """Partial JSON chunk for a tool_use block's ``input`` field."""

    id: str
    partial_json: str


@dataclass(frozen=True)
class ToolUseEnd:
    """The tool_use block closed; ``input`` is the parsed full payload."""

    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class StopReason:
    """Terminal chunk; ``reason`` is e.g. ``"end_turn"`` or ``"tool_use"``."""

    reason: str
    usage: dict[str, int] = field(default_factory=dict)


ToolStreamChunk = (
    TextDelta | ThinkingDelta | ThinkingSignature | ToolUseStart | ToolUseInputDelta | ToolUseEnd | StopReason
)


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

    async def chat_complete_async(
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

    def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
        tool_choice: dict[str, Any] | None = None,
    ) -> AsyncIterator[ToolStreamChunk]: ...
