"""Search tools: ``keyword_search`` + ``vector_search`` (Phase 5.5 placeholder).

``keyword_search`` falls back to a simple ``ILIKE`` over ledger summaries +
matrix-node titles. The Phase 5.5 work adds ``pgvector`` HNSW indexes and
turns the placeholder into a real semantic recall step; until then the
``vector_search`` tool returns ``rows=[]`` with ``truncated=True`` and a
detail string explaining the deferral so the agent can fall back to
``keyword_search``.
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
    _require_scope,
    register_tool,
)
from control_plane.agents.tools.audit import emit_tool_invocation, hash_tool_input
from control_plane.domain.canonical_memory.matrix import MatrixNode
from control_plane.domain.ledger import LedgerEvent

_DEFAULT_LIMIT = 25
_MAX_LIMIT = 100


KEYWORD_SEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "kinds": {
            "type": "array",
            "items": {"type": "string", "enum": ["event", "node"]},
            "description": "Which substrates to search; default both.",
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT},
    },
    "required": ["query"],
}

VECTOR_SEARCH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {"type": "string", "minLength": 1},
        "kinds": {"type": "array", "items": {"type": "string"}},
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT},
    },
    "required": ["query"],
}


async def keyword_search(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    query: str,
    kinds: list[str] | tuple[str, ...] | None = None,
    limit: int = _DEFAULT_LIMIT,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """ILIKE-based recall over ledger summaries + matrix node titles/attributes."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not query or not query.strip():
        raise ToolError("query must be non-empty")
    if not (1 <= limit <= _MAX_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_LIMIT}")

    search_kinds = tuple(kinds) if kinds else ("event", "node")
    like = f"%{query.strip()}%"

    rows: list[dict[str, Any]] = []
    citations: list[Citation] = []

    if "event" in search_kinds:
        ev_stmt = (
            select(LedgerEvent)
            .where(
                LedgerEvent.tenant_id == tid,
                LedgerEvent.engagement_id == eid,
                LedgerEvent.summary.ilike(like),
            )
            .order_by(LedgerEvent.occurred_at.desc())
            .limit(limit)
        )
        for ev in (await session.execute(ev_stmt)).scalars().all():
            rows.append(
                {
                    "kind": "event",
                    "id": str(ev.id),
                    "summary": ev.summary,
                    "source_kind": ev.source_kind,
                    "occurred_at": ev.occurred_at.isoformat() if ev.occurred_at else None,
                }
            )
            citations.append(Citation(kind="event", id=ev.id))

    if "node" in search_kinds:
        nd_stmt = (
            select(MatrixNode)
            .where(
                MatrixNode.tenant_id == tid,
                MatrixNode.engagement_id == eid,
                MatrixNode.title.ilike(like),
            )
            .order_by(MatrixNode.updated_at.desc())
            .limit(limit)
        )
        for n in (await session.execute(nd_stmt)).scalars().all():
            rows.append(
                {
                    "kind": "node",
                    "id": str(n.id),
                    "title": n.title,
                    "node_type": n.node_type,
                    "status": n.status,
                }
            )
            citations.append(Citation(kind="node", id=n.id))

    truncated = len(rows) >= limit
    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="keyword_search",
            input_hash=hash_tool_input({"query": query, "kinds": list(search_kinds), "limit": limit}),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len(rows),
            duration_ms=duration_ms,
            truncated=truncated,
            turn_id=turn_id,
        )
    return ToolResult(
        name="keyword_search",
        rows=rows,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
    )


async def vector_search(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    query: str,
    kinds: list[str] | tuple[str, ...] | None = None,
    limit: int = _DEFAULT_LIMIT,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Placeholder: vector search deferred to Phase 5.5 (scope-v2 §10).

    Returns ``rows=[]`` with ``truncated=True`` and a ``detail`` string so
    the LangGraph runtime in Phase 2 can recognize the deferral and route
    the query through ``keyword_search`` instead.
    """
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not query or not query.strip():
        raise ToolError("query must be non-empty")
    _ = kinds, limit  # accepted for forward-compat; ignored until Phase 5.5

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="vector_search",
            input_hash=hash_tool_input({"query": query, "kinds": list(kinds) if kinds else None, "limit": limit}),
            tenant_id=tid,
            engagement_id=eid,
            row_count=0,
            duration_ms=duration_ms,
            truncated=True,
            turn_id=turn_id,
        )
    return ToolResult(
        name="vector_search",
        rows=[],
        citations=[],
        truncated=True,
        next_cursor=None,
        duration_ms=duration_ms,
        detail="vector search deferred to Phase 5.5",
    )


register_tool(
    ToolSpec(
        name="keyword_search",
        description="ILIKE keyword recall over ledger event summaries + matrix node titles.",
        input_schema=KEYWORD_SEARCH_INPUT_SCHEMA,
    )
)
register_tool(
    ToolSpec(
        name="vector_search",
        description="Semantic vector recall (Phase 5.5 placeholder; currently returns empty).",
        input_schema=VECTOR_SEARCH_INPUT_SCHEMA,
    )
)


__all__ = [
    "KEYWORD_SEARCH_INPUT_SCHEMA",
    "VECTOR_SEARCH_INPUT_SCHEMA",
    "keyword_search",
    "vector_search",
]
