"""Ledger read tools: ``query_ledger`` + ``walk_chain``.

Both wrap the same ledger tables the ``/internal/v1/engagements/{id}/ledger``
routes expose, but as pure-function tool entrypoints with the
:class:`ToolResult` shape Kenny's LangGraph loop will consume.
"""

from __future__ import annotations

import base64
import binascii
import json
import time
import uuid
from collections import deque
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
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
from control_plane.domain.ledger import LedgerEvent, LedgerEventAffects, LedgerEventCause

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
_DEFAULT_CHAIN_DEPTH = 3
_MAX_CHAIN_DEPTH = 10
_DEFAULT_CHAIN_NODES = 200
_MAX_CHAIN_NODES = 500

QUERY_LEDGER_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "source_kind": {
            "type": "string",
            "description": "Comma-separated list of source_kind values to filter on.",
        },
        "actor_id": {"type": "string"},
        "from": {"type": "string", "format": "date-time"},
        "to": {"type": "string", "format": "date-time"},
        "affects_entity_kind": {"type": "string"},
        "affects_entity_id": {"type": "string", "format": "uuid"},
        "text": {"type": "string", "description": "Substring match on summary."},
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT},
        "cursor": {"type": "string"},
    },
}

WALK_CHAIN_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "event_id": {"type": "string", "format": "uuid"},
        "direction": {"type": "string", "enum": ["upstream", "downstream", "both"]},
        "max_depth": {"type": "integer", "minimum": 1, "maximum": _MAX_CHAIN_DEPTH},
        "max_nodes": {"type": "integer", "minimum": 1, "maximum": _MAX_CHAIN_NODES},
    },
    "required": ["event_id"],
}

INPUT_SCHEMA = QUERY_LEDGER_INPUT_SCHEMA  # back-compat alias for callers that import the canonical schema


def _encode_cursor(occurred_at: datetime, event_id: uuid.UUID) -> str:
    payload = {"o": occurred_at.isoformat(), "i": str(event_id)}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    padding = "=" * (-len(cursor) % 4)
    try:
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
        return datetime.fromisoformat(str(payload["o"])), uuid.UUID(str(payload["i"]))
    except (binascii.Error, ValueError, KeyError, TypeError) as exc:
        raise ToolError(f"invalid cursor: {cursor!r}") from exc


def _serialize_event(row: LedgerEvent) -> dict[str, Any]:
    return {
        "id": str(row.id),
        "engagement_id": str(row.engagement_id) if row.engagement_id else None,
        "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
        "actor_kind": row.actor_kind,
        "actor_id": row.actor_id,
        "source_kind": row.source_kind,
        "summary": row.summary,
        "detail": row.detail,
    }


async def query_ledger(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    source_kind: str | None = None,
    actor_id: str | None = None,
    from_: datetime | None = None,
    to: datetime | None = None,
    affects_entity_kind: str | None = None,
    affects_entity_id: uuid.UUID | str | None = None,
    text_query: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    cursor: str | None = None,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Paginated ledger search scoped to ``(tenant_id, engagement_id)``."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if limit < 1 or limit > _MAX_LIMIT:
        raise ToolError(f"limit must be between 1 and {_MAX_LIMIT}")

    stmt = select(LedgerEvent).where(
        LedgerEvent.tenant_id == tid,
        LedgerEvent.engagement_id == eid,
    )
    if source_kind is not None:
        kinds = [k.strip() for k in source_kind.split(",") if k.strip()]
        if len(kinds) == 1:
            stmt = stmt.where(LedgerEvent.source_kind == kinds[0])
        elif len(kinds) > 1:
            stmt = stmt.where(LedgerEvent.source_kind.in_(kinds))
    if actor_id is not None:
        stmt = stmt.where(LedgerEvent.actor_id == actor_id)
    if from_ is not None:
        stmt = stmt.where(LedgerEvent.occurred_at >= from_)
    if to is not None:
        stmt = stmt.where(LedgerEvent.occurred_at < to)
    if affects_entity_id is not None:
        affects_uuid = _ensure_uuid(affects_entity_id, "affects_entity_id")
        affects_subq = select(LedgerEventAffects.event_id).where(
            LedgerEventAffects.entity_id == affects_uuid,
        )
        if affects_entity_kind is not None:
            affects_subq = affects_subq.where(LedgerEventAffects.entity_kind == affects_entity_kind)
        stmt = stmt.where(LedgerEvent.id.in_(affects_subq))
    if text_query is not None and text_query.strip():
        like = f"%{text_query.strip()}%"
        stmt = stmt.where(LedgerEvent.summary.ilike(like))
    if cursor is not None:
        cursor_at, cursor_id = _decode_cursor(cursor)
        stmt = stmt.where(
            or_(
                LedgerEvent.occurred_at < cursor_at,
                (LedgerEvent.occurred_at == cursor_at) & (LedgerEvent.id < cursor_id),
            )
        )
    stmt = stmt.order_by(LedgerEvent.occurred_at.desc(), LedgerEvent.id.desc()).limit(limit + 1)

    rows = list((await session.execute(stmt)).scalars().all())
    next_cursor: str | None = None
    truncated = False
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = _encode_cursor(last.occurred_at, last.id)
        truncated = True

    serialized = [_serialize_event(r) for r in rows]
    citations = [Citation(kind="event", id=r.id) for r in rows]
    duration_ms = (time.perf_counter() - started) * 1000.0

    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="query_ledger",
            input_hash=hash_tool_input(
                {
                    "source_kind": source_kind,
                    "actor_id": actor_id,
                    "from": from_.isoformat() if from_ else None,
                    "to": to.isoformat() if to else None,
                    "affects_entity_kind": affects_entity_kind,
                    "affects_entity_id": str(affects_entity_id) if affects_entity_id else None,
                    "text": text_query,
                    "limit": limit,
                    "cursor": cursor,
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
        name="query_ledger",
        rows=serialized,
        citations=citations,
        truncated=truncated,
        next_cursor=next_cursor,
        duration_ms=duration_ms,
    )


async def walk_chain(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    event_id: uuid.UUID | str,
    direction: str = "both",
    max_depth: int = _DEFAULT_CHAIN_DEPTH,
    max_nodes: int = _DEFAULT_CHAIN_NODES,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Causal-chain walk from ``event_id`` constrained to one engagement."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    root_id = _ensure_uuid(event_id, "event_id")
    if direction not in ("upstream", "downstream", "both"):
        raise ToolError(f"direction must be upstream|downstream|both, got {direction!r}")
    if not (1 <= max_depth <= _MAX_CHAIN_DEPTH):
        raise ToolError(f"max_depth must be between 1 and {_MAX_CHAIN_DEPTH}")
    if not (1 <= max_nodes <= _MAX_CHAIN_NODES):
        raise ToolError(f"max_nodes must be between 1 and {_MAX_CHAIN_NODES}")

    root = (
        await session.execute(
            select(LedgerEvent).where(
                LedgerEvent.tenant_id == tid,
                LedgerEvent.engagement_id == eid,
                LedgerEvent.id == root_id,
            )
        )
    ).scalar_one_or_none()

    rows: list[dict[str, Any]] = []
    citations: list[Citation] = []
    truncated_node_count: int | None = None
    truncated_at_depth: int | None = None

    if root is not None:
        walk_upstream = direction in ("upstream", "both")
        walk_downstream = direction in ("downstream", "both")
        nodes: dict[uuid.UUID, LedgerEvent] = {root.id: root}
        depths: dict[uuid.UUID, int] = {root.id: 0}
        edges: set[tuple[uuid.UUID, uuid.UUID]] = set()
        truncated_ids: set[uuid.UUID] = set()
        queue: deque[tuple[uuid.UUID, int]] = deque([(root.id, 0)])
        visited: set[uuid.UUID] = {root.id}

        while queue:
            current_id, depth = queue.popleft()
            up_rows: list[uuid.UUID] = []
            down_rows: list[uuid.UUID] = []
            if walk_upstream:
                up_rows = list(
                    (
                        await session.execute(
                            select(LedgerEventCause.caused_by_id).where(LedgerEventCause.event_id == current_id)
                        )
                    )
                    .scalars()
                    .all()
                )
            if walk_downstream:
                down_rows = list(
                    (
                        await session.execute(
                            select(LedgerEventCause.event_id).where(LedgerEventCause.caused_by_id == current_id)
                        )
                    )
                    .scalars()
                    .all()
                )
            neighbor_ids: list[uuid.UUID] = [*up_rows, *down_rows]

            if depth >= max_depth:
                if any(n not in visited for n in neighbor_ids):
                    truncated_ids.add(current_id)
                    if truncated_at_depth is None or depth < truncated_at_depth:
                        truncated_at_depth = depth
                continue

            for cid in up_rows:
                edges.add((current_id, cid))
            for cid in down_rows:
                edges.add((cid, current_id))

            for neighbor_id in neighbor_ids:
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                # Re-query with tenant+engagement scope to prevent cross-tenant
                # neighbors from leaking through the cause/affect edges.
                row = (
                    await session.execute(
                        select(LedgerEvent).where(
                            LedgerEvent.tenant_id == tid,
                            LedgerEvent.engagement_id == eid,
                            LedgerEvent.id == neighbor_id,
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    continue
                if len(nodes) >= max_nodes:
                    truncated_node_count = (truncated_node_count or 0) + 1
                    continue
                nodes[neighbor_id] = row
                depths[neighbor_id] = depth + 1
                queue.append((neighbor_id, depth + 1))

        ordered = sorted(
            nodes.values(),
            key=lambda ev: (depths[ev.id], ev.occurred_at, str(ev.id)),
        )
        for ev in ordered:
            rows.append(
                {
                    **_serialize_event(ev),
                    "depth": depths[ev.id],
                    "truncated": ev.id in truncated_ids,
                }
            )
            citations.append(Citation(kind="event", id=ev.id))

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="walk_chain",
            input_hash=hash_tool_input(
                {
                    "event_id": str(root_id),
                    "direction": direction,
                    "max_depth": max_depth,
                    "max_nodes": max_nodes,
                }
            ),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len(rows),
            duration_ms=duration_ms,
            truncated=truncated_at_depth is not None or truncated_node_count is not None,
            turn_id=turn_id,
        )

    return ToolResult(
        name="walk_chain",
        rows=rows,
        citations=citations,
        truncated=truncated_at_depth is not None or truncated_node_count is not None,
        next_cursor=None,
        duration_ms=duration_ms,
        detail=(
            f"truncated_at_depth={truncated_at_depth} truncated_node_count={truncated_node_count}"
            if (truncated_at_depth is not None or truncated_node_count is not None)
            else None
        ),
    )


register_tool(
    ToolSpec(
        name="query_ledger",
        description=(
            "Paginated search over engagement ledger events. Filter by source_kind, "
            "actor_id, date range, affects-entity, or summary substring."
        ),
        input_schema=QUERY_LEDGER_INPUT_SCHEMA,
    )
)

register_tool(
    ToolSpec(
        name="walk_chain",
        description=(
            "Walk the causal chain (caused_by edges) from a starting ledger event "
            "upstream / downstream / both, bounded by max_depth + max_nodes."
        ),
        input_schema=WALK_CHAIN_INPUT_SCHEMA,
    )
)


__all__ = [
    "INPUT_SCHEMA",
    "QUERY_LEDGER_INPUT_SCHEMA",
    "WALK_CHAIN_INPUT_SCHEMA",
    "query_ledger",
    "walk_chain",
]
