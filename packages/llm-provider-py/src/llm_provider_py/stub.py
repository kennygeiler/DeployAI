from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from llm_provider_py.types import (
    CapabilityMatrix,
    ChatMessage,
    StopReason,
    StreamChunk,
    TextDelta,
    ToolStreamChunk,
    ToolUseEnd,
    ToolUseInputDelta,
    ToolUseStart,
)
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed

STUB_STREAM_REPLY = "stub streaming reply for tests"


def create_stub_provider() -> Any:
    """All capabilities True — matrix validation and tests."""

    class _Stub:
        id = "stub"

        def __init__(self) -> None:
            self.scripted_tool_calls: list[list[dict[str, Any]]] = []
            self.scripted_text: list[str] = []
            self._tool_call_idx = 0

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

        async def chat_complete_stream_with_tools(
            self,
            messages: list[ChatMessage],
            tools: list[dict[str, Any]],
            *,
            temperature: float = 0.0,
            max_output_tokens: int = 1024,
        ) -> AsyncIterator[ToolStreamChunk]:
            _ = messages, tools, temperature, max_output_tokens
            idx = self._tool_call_idx
            self._tool_call_idx += 1
            scripted = self.scripted_tool_calls[idx] if idx < len(self.scripted_tool_calls) else []
            text = self.scripted_text[idx] if idx < len(self.scripted_text) else ""
            if text:
                yield TextDelta(content=text)
            for call in scripted:
                tool_id = str(call.get("id") or f"stub_tool_{idx}_{call.get('name', '')}")
                name = str(call.get("name", ""))
                payload = call.get("input") or {}
                if not isinstance(payload, dict):
                    payload = {}
                yield ToolUseStart(id=tool_id, name=name)
                partial = json.dumps(payload)
                yield ToolUseInputDelta(id=tool_id, partial_json=partial)
                yield ToolUseEnd(id=tool_id, name=name, input=payload)
            yield StopReason(
                reason="tool_use" if scripted else "end_turn",
                usage={"input_tokens": 10, "output_tokens": 5},
            )

        def embed(self, text: str) -> list[float]:
            return pseudo_embed(text, 16)

        def capabilities(self) -> CapabilityMatrix:
            return {**DEFAULT_CAPS}

    return _Stub()
