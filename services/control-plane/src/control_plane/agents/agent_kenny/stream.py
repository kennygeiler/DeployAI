"""SSE frame formatters for Agent Kenny v2 (scope-v2 §6.3).

Frame format::

    event: <name>
    data: <json>\\n\\n
"""

from __future__ import annotations

import json
from typing import Any

from control_plane.agents.agent_kenny.types import (
    CitationUnverifiedChunk,
    CitationVerifiedChunk,
    DeltaChunk,
    DoneChunk,
    ErrorChunk,
    StreamChunk,
    ThinkingChunk,
    ToolCallChunk,
    ToolResultChunk,
)


def format_chunk(chunk: StreamChunk) -> bytes:
    """Render one :class:`StreamChunk` into one ``event:/data:`` SSE frame."""
    if isinstance(chunk, ThinkingChunk):
        return _frame("thinking", {"content": chunk.content})
    if isinstance(chunk, ToolCallChunk):
        return _frame("tool_call", {"name": chunk.name, "input": chunk.input})
    if isinstance(chunk, ToolResultChunk):
        payload: dict[str, Any] = {
            "name": chunk.name,
            "row_count": chunk.row_count,
            "truncated": chunk.truncated,
        }
        if chunk.error is not None:
            payload["error"] = chunk.error
        return _frame("tool_result", payload)
    if isinstance(chunk, DeltaChunk):
        return _frame("delta", {"content": chunk.content})
    if isinstance(chunk, CitationVerifiedChunk):
        return _frame("citation_verified", {"kind": chunk.kind, "id": chunk.identifier})
    if isinstance(chunk, CitationUnverifiedChunk):
        return _frame(
            "citation_unverified",
            {"kind": chunk.kind, "id": chunk.identifier, "outcome": chunk.outcome},
        )
    if isinstance(chunk, DoneChunk):
        return _frame(
            "done",
            {
                "turn_id": str(chunk.turn_id),
                "conversation_id": str(chunk.conversation_id),
                "tokens": chunk.tokens,
                "tool_calls": chunk.tool_calls,
                "revision_attempts": chunk.revision_attempts,
                "adversarial_concerns": chunk.adversarial_concerns,
                "final_text": chunk.final_text,
            },
        )
    if isinstance(chunk, ErrorChunk):
        return _frame("error", {"error": chunk.error})
    raise TypeError(f"unknown chunk type {type(chunk)!r}")


def _frame(event: str, payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, default=str, separators=(",", ":"))
    return f"event: {event}\ndata: {body}\n\n".encode()


__all__ = ["format_chunk"]
