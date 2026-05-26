"""Analysis tools: decision history, open risks, engagement summary.

All three are read-only aggregations over the matrix + ledger substrate.
They share the same scope + audit contract as the rest of the tool layer.
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
from control_plane.domain.canonical_memory.matrix import MatrixInsight, MatrixNode
from control_plane.domain.ledger import LedgerEvent, LedgerEventAffects

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200


GET_DECISION_HISTORY_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT},
        "status": {"type": "string"},
    },
}

GET_OPEN_RISKS_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "severity": {"type": "string", "enum": ["low", "medium", "high"]},
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT},
    },
}

GET_ENGAGEMENT_SUMMARY_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {},
}


async def get_decision_history(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    limit: int = _DEFAULT_LIMIT,
    status: str | None = None,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Decision nodes plus their most recent ``proposal_accepted`` ledger row."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not (1 <= limit <= _MAX_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_LIMIT}")

    node_stmt = select(MatrixNode).where(
        MatrixNode.tenant_id == tid,
        MatrixNode.engagement_id == eid,
        MatrixNode.node_type == "decision",
    )
    if status is not None:
        node_stmt = node_stmt.where(MatrixNode.status == status)
    node_stmt = node_stmt.order_by(MatrixNode.updated_at.desc()).limit(limit + 1)

    nodes = list((await session.execute(node_stmt)).scalars().all())
    truncated = len(nodes) > limit
    if truncated:
        nodes = nodes[:limit]

    rows: list[dict[str, Any]] = []
    citations: list[Citation] = []
    for n in nodes:
        affects_subq = select(LedgerEventAffects.event_id).where(
            LedgerEventAffects.entity_kind == "matrix_node",
            LedgerEventAffects.entity_id == n.id,
        )
        accept_stmt = (
            select(LedgerEvent)
            .where(
                LedgerEvent.tenant_id == tid,
                LedgerEvent.engagement_id == eid,
                LedgerEvent.source_kind == "proposal_accepted",
                LedgerEvent.id.in_(affects_subq),
            )
            .order_by(LedgerEvent.occurred_at.desc())
            .limit(1)
        )
        accept_row = (await session.execute(accept_stmt)).scalar_one_or_none()
        rows.append(
            {
                "id": str(n.id),
                "title": n.title,
                "status": n.status,
                "node_type": n.node_type,
                "attributes": n.attributes or {},
                "updated_at": n.updated_at.isoformat() if n.updated_at else None,
                "accepted_event_id": str(accept_row.id) if accept_row else None,
                "accepted_at": accept_row.occurred_at.isoformat() if accept_row else None,
                "accepted_summary": accept_row.summary if accept_row else None,
            }
        )
        citations.append(Citation(kind="node", id=n.id))
        if accept_row is not None:
            citations.append(Citation(kind="event", id=accept_row.id))

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="get_decision_history",
            input_hash=hash_tool_input({"limit": limit, "status": status}),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len(rows),
            duration_ms=duration_ms,
            truncated=truncated,
            turn_id=turn_id,
        )
    return ToolResult(
        name="get_decision_history",
        rows=rows,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
    )


async def get_open_risks(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    severity: str | None = None,
    limit: int = _DEFAULT_LIMIT,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Open risk matrix_insights for the engagement, with citations."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not (1 <= limit <= _MAX_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_LIMIT}")
    if severity is not None and severity not in ("low", "medium", "high"):
        raise ToolError(f"severity must be low|medium|high, got {severity!r}")

    stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tid,
        MatrixInsight.engagement_id == eid,
        MatrixInsight.insight_type == "risk",
        MatrixInsight.status == "open",
        MatrixInsight.stale.is_(False),
    )
    if severity is not None:
        stmt = stmt.where(MatrixInsight.severity == severity)
    stmt = stmt.order_by(MatrixInsight.last_refreshed_at.desc()).limit(limit + 1)

    rows_orm = list((await session.execute(stmt)).scalars().all())
    truncated = len(rows_orm) > limit
    if truncated:
        rows_orm = rows_orm[:limit]

    rows: list[dict[str, Any]] = []
    citations: list[Citation] = []
    for r in rows_orm:
        rows.append(
            {
                "id": str(r.id),
                "agent": r.agent,
                "severity": r.severity,
                "title": r.title,
                "body": r.body,
                "citation_node_ids": [str(n) for n in (r.citation_node_ids or [])],
                "citation_event_ids": [str(e) for e in (r.citation_event_ids or [])],
                "status": r.status,
            }
        )
        citations.append(Citation(kind="insight", id=r.id))
        for nid in r.citation_node_ids or []:
            citations.append(Citation(kind="node", id=nid))

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="get_open_risks",
            input_hash=hash_tool_input({"severity": severity, "limit": limit}),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len(rows),
            duration_ms=duration_ms,
            truncated=truncated,
            turn_id=turn_id,
        )
    return ToolResult(
        name="get_open_risks",
        rows=rows,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
    )


async def get_engagement_summary(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """Aggregate counts + a sample of recent events for the engagement."""
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)

    node_rows = list(
        (
            await session.execute(
                select(MatrixNode.node_type).where(
                    MatrixNode.tenant_id == tid,
                    MatrixNode.engagement_id == eid,
                )
            )
        )
        .scalars()
        .all()
    )
    counts_by_type: dict[str, int] = {}
    for nt in node_rows:
        counts_by_type[nt] = counts_by_type.get(nt, 0) + 1

    insights = list(
        (
            await session.execute(
                select(MatrixInsight.insight_type, MatrixInsight.status).where(
                    MatrixInsight.tenant_id == tid,
                    MatrixInsight.engagement_id == eid,
                )
            )
        ).all()
    )
    insights_by_type: dict[str, dict[str, int]] = {}
    for insight_type, status in insights:
        bucket = insights_by_type.setdefault(insight_type, {})
        bucket[status] = bucket.get(status, 0) + 1

    recent_events = list(
        (
            await session.execute(
                select(LedgerEvent)
                .where(LedgerEvent.tenant_id == tid, LedgerEvent.engagement_id == eid)
                .order_by(LedgerEvent.occurred_at.desc())
                .limit(10)
            )
        )
        .scalars()
        .all()
    )

    citations: list[Citation] = [Citation(kind="event", id=e.id) for e in recent_events]
    rows: list[dict[str, Any]] = [
        {
            "kind": "summary",
            "node_counts_by_type": counts_by_type,
            "insight_counts_by_type": insights_by_type,
            "total_nodes": len(node_rows),
            "total_insights": len(insights),
            "recent_event_ids": [str(e.id) for e in recent_events],
            "recent_event_summaries": [
                {"id": str(e.id), "occurred_at": e.occurred_at.isoformat(), "summary": e.summary} for e in recent_events
            ],
        }
    ]

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="get_engagement_summary",
            input_hash=hash_tool_input({}),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len(rows),
            duration_ms=duration_ms,
            turn_id=turn_id,
        )
    return ToolResult(
        name="get_engagement_summary",
        rows=rows,
        citations=citations,
        truncated=False,
        next_cursor=None,
        duration_ms=duration_ms,
    )


register_tool(
    ToolSpec(
        name="get_decision_history",
        description="Decision nodes for the engagement with their most recent proposal_accepted event.",
        input_schema=GET_DECISION_HISTORY_INPUT_SCHEMA,
    )
)
register_tool(
    ToolSpec(
        name="get_open_risks",
        description="Open risk insights for the engagement, with citation arrays.",
        input_schema=GET_OPEN_RISKS_INPUT_SCHEMA,
    )
)
register_tool(
    ToolSpec(
        name="get_engagement_summary",
        description="Aggregate snapshot: node/insight counts + sample of recent ledger events.",
        input_schema=GET_ENGAGEMENT_SUMMARY_INPUT_SCHEMA,
    )
)


__all__ = [
    "GET_DECISION_HISTORY_INPUT_SCHEMA",
    "GET_ENGAGEMENT_SUMMARY_INPUT_SCHEMA",
    "GET_OPEN_RISKS_INPUT_SCHEMA",
    "get_decision_history",
    "get_engagement_summary",
    "get_open_risks",
]
