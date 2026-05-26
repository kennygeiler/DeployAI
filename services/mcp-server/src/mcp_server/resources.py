"""MCP resource handlers (scope-v2 §8.2).

URI scheme:
- ``engagement://{id}``                — engagement summary + members + phase
- ``node://{id}``                      — matrix node full payload + 1-hop
- ``event://{id}``                     — ledger event + cause chain
- ``chain://{event_id}?...``           — causal walk
- ``search/event?q=<text>&limit=<n>``  — keyword search across ledger
- ``search/node?q=<text>&limit=<n>``   — keyword search across matrix nodes

Every handler resolves the bearer-bound principal first and rejects any
URI whose engagement scope diverges from the principal's. Cross-engagement
requests return 403 with no row leaked.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from typing import Any
from urllib.parse import parse_qsl, urlparse

from control_plane.agents.tools.ledger import walk_chain
from control_plane.agents.tools.matrix import get_matrix_node
from control_plane.agents.tools.search import keyword_search
from control_plane.domain.engagement import Engagement, EngagementMember
from control_plane.domain.ledger import LedgerEvent
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_server.audit import emit_mcp_resource_read
from mcp_server.auth import MCPPrincipal


@dataclass(frozen=True)
class ResourceContent:
    """One ``ResourceContents`` MCP frame: text/plain or JSON serialized."""

    uri: str
    mime_type: str
    text: str


class UnknownResourceError(ValueError):
    """Raised when no handler matches the requested URI scheme."""


def _parse_uri(uri: str) -> tuple[str, str, dict[str, str]]:
    """Return (scheme, path/host, query-params) for a resource URI.

    Handles two URI shapes:
    - ``scheme://host``                — engagement / node / event / chain
    - ``scheme/kind?query=...``        — search/event, search/node (path-style)
    """
    parsed = urlparse(uri)
    scheme = parsed.scheme
    host = parsed.netloc or parsed.path.lstrip("/")
    if not scheme and "/" in parsed.path:
        # search/event?q=... — split on the first '/'
        scheme, _, rest = parsed.path.partition("/")
        host = rest
    if not host and parsed.path:
        host = parsed.path.lstrip("/")
    query = dict(parse_qsl(parsed.query))
    return scheme, host, query


def _ensure_uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"{field} is not a valid UUID: {value!r}",
        ) from exc


async def _engagement_payload(
    session: AsyncSession, principal: MCPPrincipal, engagement_id: uuid.UUID
) -> dict[str, Any]:
    eng = await session.get(Engagement, engagement_id)
    if eng is None or eng.tenant_id != principal.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    members_q = await session.execute(
        select(EngagementMember).where(
            EngagementMember.tenant_id == principal.tenant_id,
            EngagementMember.engagement_id == engagement_id,
        )
    )
    members = list(members_q.scalars().all())
    return {
        "id": str(eng.id),
        "name": eng.name,
        "customer_account": eng.customer_account,
        "current_phase": eng.current_phase,
        "status": eng.status,
        "created_at": eng.created_at.isoformat(),
        "updated_at": eng.updated_at.isoformat(),
        "members": [
            {"user_id": str(m.user_id), "role": m.role, "created_at": m.created_at.isoformat()} for m in members
        ],
    }


async def _event_payload(session: AsyncSession, principal: MCPPrincipal, event_id: uuid.UUID) -> dict[str, Any]:
    engagement_id = principal.scoped_engagement()
    stmt = select(LedgerEvent).where(
        LedgerEvent.tenant_id == principal.tenant_id,
        LedgerEvent.engagement_id == engagement_id,
        LedgerEvent.id == event_id,
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    chain = await walk_chain(
        session,
        tenant_id=principal.tenant_id,
        engagement_id=engagement_id,
        event_id=event_id,
        direction="both",
        max_depth=2,
        max_nodes=50,
        emit_audit=False,
    )
    return {
        "id": str(row.id),
        "engagement_id": str(row.engagement_id) if row.engagement_id else None,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "actor_kind": row.actor_kind,
        "actor_id": row.actor_id,
        "source_kind": row.source_kind,
        "summary": row.summary,
        "detail": row.detail,
        "chain": chain.rows,
    }


async def read_resource(session: AsyncSession, principal: MCPPrincipal, uri: str) -> ResourceContent:
    """Single dispatch entry for ``resources/read``."""
    scheme, host, query = _parse_uri(uri)
    payload: dict[str, Any]
    row_count = 0
    truncated = False
    if scheme == "engagement":
        engagement_id = _ensure_uuid(host, "engagement id")
        principal.require_engagement(engagement_id)
        payload = await _engagement_payload(session, principal, engagement_id)
        row_count = 1
    elif scheme == "node":
        node_id = _ensure_uuid(host, "node id")
        engagement_id = principal.scoped_engagement()
        result = await get_matrix_node(
            session,
            tenant_id=principal.tenant_id,
            engagement_id=engagement_id,
            node_id=node_id,
            include_neighbors=True,
            emit_audit=False,
        )
        if not result.rows:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="node not found")
        payload = {"rows": result.rows, "citations": [str(c.id) for c in result.citations]}
        row_count = len(result.rows)
        truncated = result.truncated
    elif scheme == "event":
        event_id = _ensure_uuid(host, "event id")
        payload = await _event_payload(session, principal, event_id)
        row_count = 1
    elif scheme == "chain":
        event_id = _ensure_uuid(host, "event id")
        engagement_id = principal.scoped_engagement()
        direction = query.get("direction", "both")
        max_depth = int(query.get("max_depth", "3"))
        result = await walk_chain(
            session,
            tenant_id=principal.tenant_id,
            engagement_id=engagement_id,
            event_id=event_id,
            direction=direction,
            max_depth=max_depth,
            max_nodes=200,
            emit_audit=False,
        )
        payload = {"rows": result.rows, "truncated": result.truncated}
        row_count = len(result.rows)
        truncated = result.truncated
    elif scheme == "search":
        kind = host
        engagement_id = principal.scoped_engagement()
        q_text = query.get("q", "")
        limit = int(query.get("limit", "20"))
        if kind == "event":
            result = await keyword_search(
                session,
                tenant_id=principal.tenant_id,
                engagement_id=engagement_id,
                query=q_text,
                kinds=("event",),
                limit=limit,
                emit_audit=False,
            )
        elif kind == "node":
            result = await keyword_search(
                session,
                tenant_id=principal.tenant_id,
                engagement_id=engagement_id,
                query=q_text,
                kinds=("node",),
                limit=limit,
                emit_audit=False,
            )
        else:
            raise UnknownResourceError(f"unknown search kind: {kind!r}")
        payload = {"rows": result.rows, "truncated": result.truncated}
        row_count = len(result.rows)
        truncated = result.truncated
        # special-case for the deferred vector_search call path:
        if kind == "event_vector":
            payload["detail"] = "vector search deferred to Phase 5.5"
    else:
        raise UnknownResourceError(f"unknown resource scheme: {scheme!r}")

    # Audit + scope log. Best-effort; any DB failure here surfaces via the
    # outer route's exception handler — the read itself has already completed.
    await emit_mcp_resource_read(
        session,
        tenant_id=principal.tenant_id,
        engagement_id=principal.scoped_engagement(),
        api_key_id=principal.api_key_id,
        uri=uri,
        row_count=row_count,
        truncated=truncated,
    )
    await session.commit()

    return ResourceContent(uri=uri, mime_type="application/json", text=json.dumps(payload, default=str))


def list_resource_templates() -> list[dict[str, Any]]:
    """Resource templates advertised on ``resources/list``."""
    return [
        {
            "uriTemplate": "engagement://{id}",
            "name": "engagement",
            "description": "Engagement summary + members + phase.",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "node://{id}",
            "name": "node",
            "description": "Matrix node full payload plus 1-hop neighbors.",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "event://{id}",
            "name": "event",
            "description": "Ledger event row plus a 2-hop causal chain.",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "chain://{event_id}?direction=both&max_depth=3",
            "name": "chain",
            "description": "Causal walk from an event.",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "search/event?q={text}&limit=20",
            "name": "search/event",
            "description": "Keyword search across ledger event summaries.",
            "mimeType": "application/json",
        },
        {
            "uriTemplate": "search/node?q={text}&limit=20",
            "name": "search/node",
            "description": "Keyword search across matrix nodes.",
            "mimeType": "application/json",
        },
    ]


__all__ = [
    "ResourceContent",
    "UnknownResourceError",
    "list_resource_templates",
    "read_resource",
]
