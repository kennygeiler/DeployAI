"""Synthesis read tool: ``read_synthesis``.

Plain SELECT over ``matrix_insights`` filtered by the conventional Kenny
scope (``agent='kenny'`` by default — the synthesis layer Phase 0.5
writes). Accepts ``node_id`` for per-node insight lookups (e.g. the
``decision_provenance_summary`` row keyed by a decision node id via the
node's evidence linkages).
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.tools import (
    Citation,
    ToolError,
    ToolResult,
    ToolSpec,
    _ensure_uuid,
    _require_scope,
    register_tool,
)
from control_plane.agents.tools.audit import emit_tool_invocation, hash_tool_input
from control_plane.domain.canonical_memory.matrix import MatrixInsight

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


READ_SYNTHESIS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "node_id": {
            "type": "string",
            "format": "uuid",
            "description": "Filter to insights citing this matrix node.",
        },
        "agent": {"type": "string", "default": "kenny"},
        "insight_type": {"type": "string"},
        "status": {"type": "string", "enum": ["open", "dismissed", "resolved"]},
        "include_stale": {"type": "boolean", "default": False},
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT},
    },
}


def _serialize_insight(row: MatrixInsight) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "engagement_id": str(row.engagement_id) if row.engagement_id else None,
        "agent": row.agent,
        "insight_type": row.insight_type,
        "severity": row.severity,
        "title": row.title,
        "body": row.body,
        "citation_node_ids": [str(n) for n in (row.citation_node_ids or [])],
        "citation_edge_ids": [str(e) for e in (row.citation_edge_ids or [])],
        "citation_event_ids": [str(e) for e in (row.citation_event_ids or [])],
        "status": row.status,
        "stale": row.stale,
        "last_refreshed_at": row.last_refreshed_at.isoformat() if row.last_refreshed_at else None,
    }


async def read_synthesis(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_id: uuid.UUID | str | None = None,
    agent: str | None = "kenny",
    insight_type: str | None = None,
    status: str | None = None,
    include_stale: bool = False,
    limit: int = _DEFAULT_LIMIT,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Read ``matrix_insights`` for the engagement, default ``agent='kenny'``."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not (1 <= limit <= _MAX_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_LIMIT}")

    stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tid,
        MatrixInsight.engagement_id == eid,
    )
    if agent is not None:
        stmt = stmt.where(MatrixInsight.agent == agent)
    if insight_type is not None:
        stmt = stmt.where(MatrixInsight.insight_type == insight_type)
    if status is not None:
        stmt = stmt.where(MatrixInsight.status == status)
    if not include_stale:
        stmt = stmt.where(MatrixInsight.stale.is_(False))
    if node_id is not None:
        nid = _ensure_uuid(node_id, "node_id")
        # array contains: ``citation_node_ids @> ARRAY[nid]``
        stmt = stmt.where(MatrixInsight.citation_node_ids.contains([nid]))

    stmt = stmt.order_by(MatrixInsight.last_refreshed_at.desc()).limit(limit + 1)
    rows = list((await session.execute(stmt)).scalars().all())
    truncated = len(rows) > limit
    if truncated:
        rows = rows[:limit]

    serialized = [_serialize_insight(r) for r in rows]
    citations: list[Citation] = []
    for r in rows:
        citations.append(Citation(kind="insight", id=r.id))
        for nid in r.citation_node_ids or []:
            citations.append(Citation(kind="node", id=nid))
        for ev in r.citation_event_ids or []:
            citations.append(Citation(kind="event", id=ev))

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="read_synthesis",
            input_hash=hash_tool_input(
                {
                    "node_id": str(node_id) if node_id else None,
                    "agent": agent,
                    "insight_type": insight_type,
                    "status": status,
                    "include_stale": include_stale,
                    "limit": limit,
                }
            ),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len(rows),
            duration_ms=duration_ms,
            truncated=truncated,
            turn_id=turn_id,
        )
    return ToolResult(
        name="read_synthesis",
        rows=serialized,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
    )


register_tool(
    ToolSpec(
        name="read_synthesis",
        description=(
            "Read compounding-synthesis rows (matrix_insights) authored by Kenny "
            "for the engagement, optionally filtered by node_id / insight_type / status."
        ),
        input_schema=READ_SYNTHESIS_INPUT_SCHEMA,
    )
)

__all__ = ["READ_SYNTHESIS_INPUT_SCHEMA", "read_synthesis"]
