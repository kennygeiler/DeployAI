"""MCP tool exposure layer (scope-v2 §8.3).

Wires the Phase 1 read tools as MCP ``Tool`` definitions. ``propose_action``
is the write tool and is NOT exposed here — even an advisor with a valid
token cannot mutate engagement state through the MCP server.

Each MCP tool resolves to the underlying Phase 1 function. Inputs are
JSON dicts validated against the registered ``input_schema``; outputs are
the Phase 1 :class:`ToolResult` rendered as JSON for MCP ``CallToolResult``.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import Any

from control_plane.agents.tools import TOOL_REGISTRY, ToolError, ToolResult
from control_plane.agents.tools.analysis import (
    get_decision_history,
    get_engagement_summary,
    get_open_risks,
)
from control_plane.agents.tools.ledger import query_ledger, walk_chain
from control_plane.agents.tools.matrix import (
    get_matrix_neighbors,
    get_matrix_node,
    get_matrix_subgraph,
)
from control_plane.agents.tools.search import keyword_search, vector_search
from control_plane.agents.tools.synthesis import read_synthesis
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_server.audit import emit_mcp_tool_call
from mcp_server.auth import MCPPrincipal

ToolHandler = Callable[..., Awaitable[ToolResult]]

# Read tools only. ``propose_action`` lives in
# ``control_plane.agents.tools.escalate`` and is intentionally absent here.
READ_TOOL_HANDLERS: dict[str, ToolHandler] = {
    "query_ledger": query_ledger,
    "walk_chain": walk_chain,
    "get_matrix_node": get_matrix_node,
    "get_matrix_neighbors": get_matrix_neighbors,
    "get_matrix_subgraph": get_matrix_subgraph,
    "read_synthesis": read_synthesis,
    "get_decision_history": get_decision_history,
    "get_open_risks": get_open_risks,
    "get_engagement_summary": get_engagement_summary,
    "vector_search": vector_search,
    "keyword_search": keyword_search,
}

# Hard guarantee: no write tool ever lands in the MCP-exposed set.
FORBIDDEN_TOOLS: frozenset[str] = frozenset({"propose_action"})


def list_mcp_tools() -> list[dict[str, Any]]:
    """Tools advertised by ``tools/list`` per the MCP spec."""
    out: list[dict[str, Any]] = []
    for name in sorted(READ_TOOL_HANDLERS):
        if name in FORBIDDEN_TOOLS:
            continue
        spec = TOOL_REGISTRY.get(name)
        if spec is None:
            continue
        out.append(
            {
                "name": name,
                "description": spec.description,
                "inputSchema": spec.input_schema,
            }
        )
    return out


def _coerce_optional_uuid(value: Any) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    if isinstance(value, str):
        try:
            return uuid.UUID(value)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid UUID: {value!r}",
            ) from exc
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"expected UUID, got {type(value).__name__}",
    )


def _coerce_optional_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"invalid datetime: {value!r}",
            ) from exc
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"expected ISO datetime, got {type(value).__name__}",
    )


def _build_kwargs(name: str, raw: dict[str, Any]) -> dict[str, Any]:
    """Map MCP-style input keys onto Phase 1 tool keyword arguments."""
    if name == "query_ledger":
        return {
            "source_kind": raw.get("source_kind"),
            "actor_id": raw.get("actor_id"),
            "from_": _coerce_optional_datetime(raw.get("from")),
            "to": _coerce_optional_datetime(raw.get("to")),
            "affects_entity_kind": raw.get("affects_entity_kind"),
            "affects_entity_id": _coerce_optional_uuid(raw.get("affects_entity_id")),
            "text_query": raw.get("text"),
            "limit": int(raw.get("limit", 50)),
            "cursor": raw.get("cursor"),
        }
    if name == "walk_chain":
        event_id = _coerce_optional_uuid(raw.get("event_id"))
        if event_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="event_id is required for walk_chain",
            )
        return {
            "event_id": event_id,
            "direction": raw.get("direction", "both"),
            "max_depth": int(raw.get("max_depth", 3)),
            "max_nodes": int(raw.get("max_nodes", 200)),
        }
    if name in ("get_matrix_node", "get_matrix_neighbors"):
        node_id = _coerce_optional_uuid(raw.get("node_id"))
        if node_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="node_id is required",
            )
        if name == "get_matrix_node":
            return {"node_id": node_id, "include_neighbors": bool(raw.get("include_neighbors", True))}
        return {
            "node_id": node_id,
            "k": int(raw.get("k", 1)),
            "edge_types": raw.get("edge_types"),
            "limit": int(raw.get("limit", 100)),
        }
    if name == "get_matrix_subgraph":
        return {
            "node_types": raw.get("node_types"),
            "edge_types": raw.get("edge_types"),
            "since": _coerce_optional_datetime(raw.get("since")),
            "limit": int(raw.get("limit", 100)),
        }
    if name == "read_synthesis":
        return {
            "node_id": _coerce_optional_uuid(raw.get("node_id")),
            "agent": raw.get("agent", "kenny"),
            "insight_type": raw.get("insight_type"),
            "status": raw.get("status"),
            "include_stale": bool(raw.get("include_stale", False)),
            "limit": int(raw.get("limit", 50)),
        }
    if name == "get_decision_history":
        return {"limit": int(raw.get("limit", 50)), "status": raw.get("status")}
    if name == "get_open_risks":
        return {"severity": raw.get("severity"), "limit": int(raw.get("limit", 50))}
    if name == "get_engagement_summary":
        return {}
    if name in ("keyword_search", "vector_search"):
        q = raw.get("query")
        if not isinstance(q, str) or not q.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="query is required",
            )
        return {
            "query": q,
            "kinds": raw.get("kinds"),
            "limit": int(raw.get("limit", 25)),
        }
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown tool: {name!r}")


def _result_payload(result: ToolResult) -> dict[str, Any]:
    return {
        "name": result.name,
        "rows": result.rows,
        "citations": [{"kind": c.kind, "id": str(c.id)} for c in result.citations],
        "truncated": result.truncated,
        "next_cursor": result.next_cursor,
        "duration_ms": result.duration_ms,
        "detail": result.detail,
    }


async def call_tool(
    session: AsyncSession,
    principal: MCPPrincipal,
    *,
    name: str,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Single dispatch entry for ``tools/call``."""
    if name in FORBIDDEN_TOOLS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"tool {name!r} is not exposed via MCP",
        )
    handler = READ_TOOL_HANDLERS.get(name)
    if handler is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown tool: {name!r}")
    engagement_id = principal.scoped_engagement()
    kwargs = _build_kwargs(name, arguments)
    started = time.perf_counter()
    try:
        result = await handler(
            session,
            tenant_id=principal.tenant_id,
            engagement_id=engagement_id,
            emit_audit=False,
            **kwargs,
        )
    except ToolError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    duration_ms = (time.perf_counter() - started) * 1000.0

    await emit_mcp_tool_call(
        session,
        tenant_id=principal.tenant_id,
        engagement_id=engagement_id,
        api_key_id=principal.api_key_id,
        tool_name=name,
        row_count=len(result.rows),
        duration_ms=duration_ms,
        truncated=result.truncated,
    )
    await session.commit()
    return _result_payload(result)


__all__ = [
    "FORBIDDEN_TOOLS",
    "READ_TOOL_HANDLERS",
    "call_tool",
    "list_mcp_tools",
]
