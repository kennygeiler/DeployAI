"""Audit emit helper used by every tool in the v2 Phase 1 tool layer.

One ledger row per tool call, regardless of success / empty / failure.
The row carries a SHA-256 hash of the redacted input (never raw secrets)
plus row count and ``duration_ms`` so a Phase 3 verifier can correlate
tool invocations with the citations Agent Kenny emits.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.ledger import emit_ledger_event

_INPUT_HASH_LEN = 32


def hash_tool_input(input_payload: dict[str, Any]) -> str:
    """SHA-256 hash of a deterministic JSON encoding of ``input_payload``.

    Used so the ledger row carries auditable evidence of *what* the LLM
    asked the tool to do without persisting the raw arguments (which may
    contain secrets or PII verbatim from the model's prior turns).
    """
    encoded = json.dumps(input_payload, sort_keys=True, default=_json_fallback).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:_INPUT_HASH_LEN]


def _json_fallback(value: Any) -> Any:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return repr(value)


async def emit_tool_invocation(
    session: AsyncSession,
    *,
    tool_name: str,
    input_hash: str,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    row_count: int,
    duration_ms: float,
    truncated: bool = False,
    turn_id: uuid.UUID | None = None,
) -> uuid.UUID:
    """Append one ``agent_tool_invocation`` row tied to a tool call.

    Returns the ledger event id so the caller can stitch ``caused_by`` from
    later citation-verification events in Phase 3.
    """
    summary = f"tool:{tool_name} rows={row_count} dur={duration_ms:.1f}ms"
    detail: dict[str, Any] = {
        "tool_name": tool_name,
        "input_hash": input_hash,
        "row_count": int(row_count),
        "duration_ms": round(float(duration_ms), 2),
        "truncated": bool(truncated),
    }
    if turn_id is not None:
        detail["turn_id"] = str(turn_id)
    row = await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="agent",
        actor_id="kenny",
        source_kind="agent_tool_invocation",
        source_ref=None,
        summary=summary[:500],
        detail=detail,
    )
    return row.id


__all__ = ["emit_tool_invocation", "hash_tool_input"]
