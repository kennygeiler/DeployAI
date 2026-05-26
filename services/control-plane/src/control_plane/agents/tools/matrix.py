"""Matrix read tools: ``get_matrix_node``, ``get_matrix_neighbors``, ``get_matrix_subgraph``.

The first hits ``matrix_nodes`` + ``matrix_edges`` over plain SQL. The
remaining two prefer the Apache AGE Cypher path (installed in Phase 0a)
and fall back to a recursive CTE if AGE isn't loaded — see
``cypher_query`` in :mod:`control_plane.agents.tools.graph` for the
isolation contract.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select, text
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
from control_plane.agents.tools.graph import CypherIsolationError, cypher_query
from control_plane.domain.canonical_memory.matrix import MatrixEdge, MatrixNode

_DEFAULT_NEIGHBOR_LIMIT = 100
_MAX_NEIGHBOR_LIMIT = 500
_MAX_K_HOP = 4


GET_MATRIX_NODE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "node_id": {"type": "string", "format": "uuid"},
        "include_neighbors": {"type": "boolean", "default": True},
    },
    "required": ["node_id"],
}

GET_MATRIX_NEIGHBORS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "node_id": {"type": "string", "format": "uuid"},
        "k": {"type": "integer", "minimum": 1, "maximum": _MAX_K_HOP, "default": 1},
        "edge_types": {"type": "array", "items": {"type": "string"}},
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_NEIGHBOR_LIMIT},
    },
    "required": ["node_id"],
}

GET_MATRIX_SUBGRAPH_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "node_types": {"type": "array", "items": {"type": "string"}},
        "edge_types": {"type": "array", "items": {"type": "string"}},
        "since": {"type": "string", "format": "date-time"},
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_NEIGHBOR_LIMIT},
    },
}


def _serialize_node(row: MatrixNode) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "engagement_id": str(row.engagement_id),
        "node_type": row.node_type,
        "title": row.title,
        "status": row.status,
        "attributes": row.attributes or {},
        "evidence_event_ids": [str(e) for e in (row.evidence_event_ids or [])],
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _serialize_edge(row: MatrixEdge) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "engagement_id": str(row.engagement_id),
        "edge_type": row.edge_type,
        "from_node_id": str(row.from_node_id),
        "to_node_id": str(row.to_node_id),
        "attributes": row.attributes or {},
        "evidence_event_ids": [str(e) for e in (row.evidence_event_ids or [])],
    }


async def get_matrix_node(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_id: uuid.UUID | str,
    include_neighbors: bool = True,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Return one matrix node + (optionally) its 1-hop neighbors via SQL."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    nid = _ensure_uuid(node_id, "node_id")

    node_row = (
        await session.execute(
            select(MatrixNode).where(
                MatrixNode.tenant_id == tid,
                MatrixNode.engagement_id == eid,
                MatrixNode.id == nid,
            )
        )
    ).scalar_one_or_none()

    rows: list[dict[str, Any]] = []
    citations: list[Citation] = []
    if node_row is not None:
        serialized = _serialize_node(node_row)
        rows.append({"kind": "node", **serialized})
        citations.append(Citation(kind="node", id=node_row.id))
        for ev_id in node_row.evidence_event_ids or []:
            citations.append(Citation(kind="event", id=ev_id))

        if include_neighbors:
            edge_rows = list(
                (
                    await session.execute(
                        select(MatrixEdge).where(
                            MatrixEdge.tenant_id == tid,
                            MatrixEdge.engagement_id == eid,
                            or_(MatrixEdge.from_node_id == nid, MatrixEdge.to_node_id == nid),
                        )
                    )
                )
                .scalars()
                .all()
            )
            neighbor_ids = {(e.to_node_id if e.from_node_id == nid else e.from_node_id) for e in edge_rows}
            neighbor_rows: dict[uuid.UUID, MatrixNode] = {}
            if neighbor_ids:
                neighbor_query = await session.execute(
                    select(MatrixNode).where(
                        MatrixNode.tenant_id == tid,
                        MatrixNode.engagement_id == eid,
                        MatrixNode.id.in_(list(neighbor_ids)),
                    )
                )
                neighbor_rows = {n.id: n for n in neighbor_query.scalars().all()}
            for nb in neighbor_rows.values():
                rows.append({"kind": "neighbor", **_serialize_node(nb)})
                citations.append(Citation(kind="node", id=nb.id))
            for e in edge_rows:
                rows.append({"kind": "edge", **_serialize_edge(e)})
                citations.append(Citation(kind="edge", id=e.id))

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="get_matrix_node",
            input_hash=hash_tool_input({"node_id": str(nid), "include_neighbors": include_neighbors}),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len(rows),
            duration_ms=duration_ms,
            turn_id=turn_id,
        )
    return ToolResult(
        name="get_matrix_node",
        rows=rows,
        citations=citations,
        truncated=False,
        next_cursor=None,
        duration_ms=duration_ms,
    )


async def _age_available(session: AsyncSession) -> bool:
    """Return True iff the AGE extension is installed in the current DB."""
    try:
        result = await session.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'age'"))
        return result.first() is not None
    except Exception:
        return False


async def _neighbors_via_cypher(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_id: uuid.UUID,
    k: int,
    edge_types: tuple[str, ...] | None,
    limit: int,
) -> list[uuid.UUID]:
    """k-hop neighbors via AGE Cypher. Returns the neighbor node UUIDs."""
    edge_label = ""
    if edge_types:
        safe = [e.replace("'", "").replace("`", "") for e in edge_types if e.isidentifier()]
        if safe:
            edge_label = ":" + "|".join(safe)
    cypher = (
        f"MATCH (n:matrix_node {{id: '{node_id}', tenant_id: '{tenant_id}', engagement_id: '{engagement_id}'}}) "
        f"-[r{edge_label}*1..{k}]-(m:matrix_node {{tenant_id: '{tenant_id}', engagement_id: '{engagement_id}'}}) "
        f"WHERE m.id <> '{node_id}' "
        f"RETURN DISTINCT m.id AS mid LIMIT {limit}"
    )
    try:
        rows = await cypher_query(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            cypher=cypher,
            return_columns=["mid"],
        )
    except CypherIsolationError:
        raise
    out: list[uuid.UUID] = []
    for row in rows:
        raw = row.get("mid")
        if raw is None:
            continue
        # AGE returns agtype-wrapped strings ("\"uuid\"") for scalar returns.
        candidate = str(raw).strip().strip('"')
        try:
            out.append(uuid.UUID(candidate))
        except ValueError:
            continue
    return out


async def _neighbors_via_cte(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_id: uuid.UUID,
    k: int,
    edge_types: tuple[str, ...] | None,
    limit: int,
) -> list[uuid.UUID]:
    """Recursive-CTE fallback when AGE isn't loaded.

    ``walk`` is keyed by depth so the same node visited at multiple depths
    expands its neighbors at each level (cycle protection happens through
    the ``UNION`` + recursion-depth cap).
    """
    params: dict[str, Any] = {
        "tid": str(tenant_id),
        "eid": str(engagement_id),
        "root": str(node_id),
        "lim": limit,
        "k_max": k,
    }
    edge_clause = ""
    if edge_types:
        edge_clause = "AND e.edge_type = ANY(:edge_types)"
        params["edge_types"] = list(edge_types)
    sql = text(
        f"""
        WITH RECURSIVE walk(node_id, depth) AS (
            SELECT CAST(:root AS uuid), 0
            UNION
            SELECT
                CASE WHEN e.from_node_id = w.node_id THEN e.to_node_id ELSE e.from_node_id END,
                w.depth + 1
            FROM walk w
            JOIN matrix_edges e
              ON (e.from_node_id = w.node_id OR e.to_node_id = w.node_id)
            WHERE e.tenant_id = CAST(:tid AS uuid)
              AND e.engagement_id = CAST(:eid AS uuid)
              AND w.depth < :k_max
              {edge_clause}
        )
        SELECT DISTINCT node_id
        FROM walk
        WHERE node_id <> CAST(:root AS uuid)
        LIMIT :lim
        """
    )
    result = await session.execute(sql, params)
    return [row[0] for row in result.all()]


async def get_matrix_neighbors(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_id: uuid.UUID | str,
    k: int = 1,
    edge_types: list[str] | tuple[str, ...] | None = None,
    limit: int = _DEFAULT_NEIGHBOR_LIMIT,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """k-hop neighbors of ``node_id`` via Cypher when available, CTE otherwise."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    nid = _ensure_uuid(node_id, "node_id")
    if not (1 <= k <= _MAX_K_HOP):
        raise ToolError(f"k must be between 1 and {_MAX_K_HOP}")
    if not (1 <= limit <= _MAX_NEIGHBOR_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_NEIGHBOR_LIMIT}")

    et = tuple(edge_types) if edge_types else None

    root = (
        await session.execute(
            select(MatrixNode.id).where(
                MatrixNode.tenant_id == tid,
                MatrixNode.engagement_id == eid,
                MatrixNode.id == nid,
            )
        )
    ).scalar_one_or_none()

    rows: list[dict[str, Any]] = []
    citations: list[Citation] = []
    truncated = False

    if root is not None:
        neighbor_ids: list[uuid.UUID] = []
        if await _age_available(session):
            try:
                neighbor_ids = await _neighbors_via_cypher(
                    session,
                    tenant_id=tid,
                    engagement_id=eid,
                    node_id=nid,
                    k=k,
                    edge_types=et,
                    limit=limit + 1,
                )
            except Exception:
                neighbor_ids = await _neighbors_via_cte(
                    session,
                    tenant_id=tid,
                    engagement_id=eid,
                    node_id=nid,
                    k=k,
                    edge_types=et,
                    limit=limit + 1,
                )
        else:
            neighbor_ids = await _neighbors_via_cte(
                session,
                tenant_id=tid,
                engagement_id=eid,
                node_id=nid,
                k=k,
                edge_types=et,
                limit=limit + 1,
            )

        if len(neighbor_ids) > limit:
            neighbor_ids = neighbor_ids[:limit]
            truncated = True

        if neighbor_ids:
            full = list(
                (
                    await session.execute(
                        select(MatrixNode).where(
                            MatrixNode.tenant_id == tid,
                            MatrixNode.engagement_id == eid,
                            MatrixNode.id.in_(neighbor_ids),
                        )
                    )
                )
                .scalars()
                .all()
            )
            for n in full:
                rows.append(_serialize_node(n))
                citations.append(Citation(kind="node", id=n.id))

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="get_matrix_neighbors",
            input_hash=hash_tool_input(
                {
                    "node_id": str(nid),
                    "k": k,
                    "edge_types": list(et) if et else None,
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
        name="get_matrix_neighbors",
        rows=rows,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
    )


async def get_matrix_subgraph(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_types: list[str] | tuple[str, ...] | None = None,
    edge_types: list[str] | tuple[str, ...] | None = None,
    since: datetime | None = None,
    limit: int = _DEFAULT_NEIGHBOR_LIMIT,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Bounded subgraph filtered by ``node_types`` / ``edge_types`` / ``since``."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not (1 <= limit <= _MAX_NEIGHBOR_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_NEIGHBOR_LIMIT}")

    node_stmt = select(MatrixNode).where(
        MatrixNode.tenant_id == tid,
        MatrixNode.engagement_id == eid,
    )
    if node_types:
        node_stmt = node_stmt.where(MatrixNode.node_type.in_(list(node_types)))
    if since is not None:
        node_stmt = node_stmt.where(MatrixNode.updated_at >= since)
    node_stmt = node_stmt.order_by(MatrixNode.updated_at.desc()).limit(limit + 1)

    node_rows = list((await session.execute(node_stmt)).scalars().all())
    truncated = len(node_rows) > limit
    if truncated:
        node_rows = node_rows[:limit]

    node_ids = [n.id for n in node_rows]

    edge_rows: list[MatrixEdge] = []
    if node_ids:
        edge_stmt = select(MatrixEdge).where(
            MatrixEdge.tenant_id == tid,
            MatrixEdge.engagement_id == eid,
            MatrixEdge.from_node_id.in_(node_ids),
            MatrixEdge.to_node_id.in_(node_ids),
        )
        if edge_types:
            edge_stmt = edge_stmt.where(MatrixEdge.edge_type.in_(list(edge_types)))
        if since is not None:
            edge_stmt = edge_stmt.where(MatrixEdge.updated_at >= since)
        edge_stmt = edge_stmt.limit(_MAX_NEIGHBOR_LIMIT)
        edge_rows = list((await session.execute(edge_stmt)).scalars().all())

    rows: list[dict[str, Any]] = []
    citations: list[Citation] = []
    for n in node_rows:
        rows.append({"kind": "node", **_serialize_node(n)})
        citations.append(Citation(kind="node", id=n.id))
    for e in edge_rows:
        rows.append({"kind": "edge", **_serialize_edge(e)})
        citations.append(Citation(kind="edge", id=e.id))

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="get_matrix_subgraph",
            input_hash=hash_tool_input(
                {
                    "node_types": list(node_types) if node_types else None,
                    "edge_types": list(edge_types) if edge_types else None,
                    "since": since.isoformat() if since else None,
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
        name="get_matrix_subgraph",
        rows=rows,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
    )


register_tool(
    ToolSpec(
        name="get_matrix_node",
        description="Fetch one matrix node by id plus (optionally) its 1-hop neighbors and edges.",
        input_schema=GET_MATRIX_NODE_INPUT_SCHEMA,
    )
)
register_tool(
    ToolSpec(
        name="get_matrix_neighbors",
        description="k-hop neighbors of a matrix node, optionally filtered by edge_type.",
        input_schema=GET_MATRIX_NEIGHBORS_INPUT_SCHEMA,
    )
)
register_tool(
    ToolSpec(
        name="get_matrix_subgraph",
        description="Bounded subgraph filtered by node_types / edge_types / since timestamp.",
        input_schema=GET_MATRIX_SUBGRAPH_INPUT_SCHEMA,
    )
)


__all__ = [
    "GET_MATRIX_NEIGHBORS_INPUT_SCHEMA",
    "GET_MATRIX_NODE_INPUT_SCHEMA",
    "GET_MATRIX_SUBGRAPH_INPUT_SCHEMA",
    "get_matrix_neighbors",
    "get_matrix_node",
    "get_matrix_subgraph",
]
