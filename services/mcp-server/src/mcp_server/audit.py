"""Audit emit: every external MCP call leaves one ledger row in the CP DB.

We reuse ``control_plane.ledger.emit_ledger_event`` rather than POSTing to a
new CP route — the MCP server already has a session against the same DB, so
the dual-write semantics are simpler when we just append the row inline.

Source kinds (declared in ``control_plane.ledger.emitter.ALLOWED_SOURCE_KINDS``):
- ``mcp_resource_read`` for any ``resources/read`` request.
- ``mcp_tool_invocation`` for any ``tools/call`` request.
- ``mcp_auth_failed`` for visibility into spike attacks (called from middleware).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from control_plane.ledger import emit_ledger_event
from sqlalchemy.ext.asyncio import AsyncSession


async def emit_mcp_resource_read(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    api_key_id: uuid.UUID,
    uri: str,
    row_count: int,
    truncated: bool = False,
) -> None:
    """One row per MCP ``resources/read`` request."""
    detail: dict[str, Any] = {
        "uri": uri[:500],
        "api_key_id": str(api_key_id),
        "row_count": int(row_count),
        "truncated": bool(truncated),
    }
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="agent",
        actor_id=f"mcp:{api_key_id}",
        source_kind="mcp_resource_read",
        source_ref=None,
        summary=f"mcp resource read {uri[:200]}",
        detail=detail,
    )


async def emit_mcp_tool_call(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    api_key_id: uuid.UUID,
    tool_name: str,
    row_count: int,
    duration_ms: float,
    truncated: bool = False,
) -> None:
    """One row per MCP ``tools/call`` request."""
    detail: dict[str, Any] = {
        "tool_name": tool_name,
        "api_key_id": str(api_key_id),
        "row_count": int(row_count),
        "duration_ms": round(float(duration_ms), 2),
        "truncated": bool(truncated),
    }
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="agent",
        actor_id=f"mcp:{api_key_id}",
        source_kind="mcp_tool_invocation",
        source_ref=None,
        summary=f"mcp tool {tool_name}",
        detail=detail,
    )


__all__ = ["emit_mcp_resource_read", "emit_mcp_tool_call"]
