from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Literal, Protocol, runtime_checkable

ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: ChatRole
    content: str


@dataclass(frozen=True, slots=True)
class LLMCallOptions:
    temperature: float | None = None
    max_output_tokens: int | None = None


@dataclass(frozen=True, slots=True)
class CapabilityMatrix:
    extraction: bool = False
    retrieval: bool = False
    arbitration: bool = False
    embeddings: bool = False
    tool_use: bool = False

    def to_dict(self) -> dict[str, bool]:
        return {
            "extraction": self.extraction,
            "retrieval": self.retrieval,
            "arbitration": self.arbitration,
            "embeddings": self.embeddings,
            "tool_use": self.tool_use,
        }


stub_capabilities: ClassVar[CapabilityMatrix] = CapabilityMatrix(
    extraction=True,
    retrieval=True,
    arbitration=True,
    embeddings=True,
    tool_use=True,
)


@runtime_checkable
class LLMProvider(Protocol):
    id: str

    def chat_complete(
        self,
        messages: tuple[ChatMessage, ...] | list[ChatMessage],
        options: LLMCallOptions | None = None,
    ) -> str: ...
    def embed(self, text: str) -> list[float]: ...
    def capabilities(self) -> CapabilityMatrix: ...


@dataclass
class _Stub:
    _prefix: str = "stub-out"

    id: str = "stub"

    def chat_complete(
        self,
        messages: tuple[ChatMessage, ...] | list[ChatMessage],
        options: LLMCallOptions | None = None,
    ) -> str:
        _ = options
        user_like = [m for m in messages if m.role != "system"]
        last = user_like[-1].content if user_like else ""
        return f"{self._prefix}:{len(last)}"

    def embed(self, text: str) -> list[float]:
        return [float(len(text)), float(ord(text[0]) & 0xFF) if text else 0.0, 0.25, 0.5]

    def capabilities(self) -> CapabilityMatrix:
        return stub_capabilities


def create_stub_provider(prefix: str = "stub-out") -> LLMProvider:
    return _Stub(_prefix=prefix)
