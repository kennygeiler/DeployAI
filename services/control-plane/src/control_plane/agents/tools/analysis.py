"""Analysis tools: decision history, open risks, engagement summary,
list-nodes-by-type.

All four are read-only aggregations over the matrix + ledger substrate.
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
from control_plane.domain.canonical_memory.matrix import (
    MATRIX_NODE_TYPES,
    MatrixInsight,
    MatrixNode,
)
from control_plane.domain.ledger import LedgerEvent, LedgerEventAffects

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 200
_DESCRIPTION_CAP = 500
_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


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

LIST_MATRIX_NODES_BY_TYPE_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "node_type": {
            "type": "string",
            "description": (
                "Catalog node type — one of stakeholder, organization, system, "
                "decision, risk, commitment, opportunity. Custom tenant types "
                "are also accepted at runtime."
            ),
        },
        "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LIMIT},
    },
    "required": ["node_type"],
}


def _node_description(node: MatrixNode) -> str | None:
    """Extract a human-readable description from ``attributes`` JSONB.

    ``matrix_nodes`` has no top-level ``description`` column; the
    convention (see ``workers/synthesizer.py`` + ``workers/wiki_lint.py``)
    is to store it under ``attributes.description``. We also tolerate
    ``body``/``notes`` as fallbacks so the LLM still surfaces something
    if a feeder agent used a divergent key.
    """
    attrs = node.attributes or {}
    for key in ("description", "body", "notes", "summary"):
        value = attrs.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _truncate(text: str | None, cap: int = _DESCRIPTION_CAP) -> str | None:
    if text is None:
        return None
    if len(text) <= cap:
        return text
    return text[:cap] + "..."


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
    """Union of open risk matrix_insights AND raw risk-typed matrix_nodes.

    The synthesis layer (``matrix_insights`` rows authored by Kenny / Oracle)
    is preferred — insights compound multiple evidence events into a single
    titled body with severity. But until that layer runs, the only place a
    risk lives is the raw ``matrix_nodes`` table. Returning both lets Kenny
    answer "what are the major risks?" end-to-end even on cold engagements.

    Result shape (additive — old keys still present on insight rows):
      ``source``: ``"insight"`` or ``"node"``
      ``id``, ``title``, ``description`` (≤500 chars), ``severity``
        (insights only), ``evidence_event_ids``, ``occurred_at``

    Ordering: insights first (high > medium > low > unset by severity), then
    raw nodes (most recent first). Capped at ``limit`` total rows.

    Citations: each insight contributes its ``citation_event_ids`` +
    ``citation_node_ids`` as kinded UUIDs; each node contributes its
    ``evidence_event_ids`` as ``event`` citations plus its own node id.
    """
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not (1 <= limit <= _MAX_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_LIMIT}")
    if severity is not None and severity not in ("low", "medium", "high"):
        raise ToolError(f"severity must be low|medium|high, got {severity!r}")

    insight_stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tid,
        MatrixInsight.engagement_id == eid,
        MatrixInsight.insight_type == "risk",
        MatrixInsight.status == "open",
        MatrixInsight.stale.is_(False),
    )
    if severity is not None:
        insight_stmt = insight_stmt.where(MatrixInsight.severity == severity)
    insight_stmt = insight_stmt.order_by(MatrixInsight.last_refreshed_at.desc()).limit(limit + 1)

    insight_rows = list((await session.execute(insight_stmt)).scalars().all())

    # When a severity filter is set, raw nodes can't satisfy it (nodes have
    # no severity column) so we return insight rows only. This keeps the
    # ``severity='high'`` callers (existing back-compat test) on the
    # insights-only path.
    node_rows: list[MatrixNode] = []
    if severity is None:
        node_stmt = select(MatrixNode).where(
            MatrixNode.tenant_id == tid,
            MatrixNode.engagement_id == eid,
            MatrixNode.node_type == "risk",
        )
        # Treat NULL status as "not archived" — early matrix rows often
        # have no status field populated yet.
        node_stmt = node_stmt.where(
            (MatrixNode.status.is_(None)) | (MatrixNode.status != "archived"),
        )
        node_stmt = node_stmt.order_by(MatrixNode.updated_at.desc()).limit(limit + 1)
        node_rows = list((await session.execute(node_stmt)).scalars().all())

    # Build serialized output. Insights first, sorted by severity bucket
    # then refresh recency.
    insight_payloads: list[dict[str, Any]] = []
    for r in insight_rows:
        insight_payloads.append(
            {
                "source": "insight",
                "id": str(r.id),
                "title": r.title,
                "description": _truncate(r.body),
                "severity": r.severity,
                "agent": r.agent,
                "status": r.status,
                "evidence_event_ids": [str(e) for e in (r.citation_event_ids or [])],
                "citation_node_ids": [str(n) for n in (r.citation_node_ids or [])],
                # Back-compat alias for callers that still read ``body``:
                "body": r.body,
                # Back-compat alias for callers that still read
                # ``citation_event_ids``:
                "citation_event_ids": [str(e) for e in (r.citation_event_ids or [])],
                "occurred_at": (r.last_refreshed_at.isoformat() if r.last_refreshed_at else None),
            }
        )
    insight_payloads.sort(
        key=lambda row: (
            _SEVERITY_ORDER.get(str(row.get("severity") or ""), 99),
            # negative iso-string sort ≈ desc by recency; fall back to "" for
            # unset
            -(_iso_to_sort_key(row.get("occurred_at"))),
        )
    )

    node_payloads: list[dict[str, Any]] = []
    for n in node_rows:
        node_payloads.append(
            {
                "source": "node",
                "id": str(n.id),
                "title": n.title,
                "description": _truncate(_node_description(n)),
                "severity": None,
                "status": n.status,
                "node_type": n.node_type,
                "evidence_event_ids": [str(e) for e in (n.evidence_event_ids or [])],
                "occurred_at": n.updated_at.isoformat() if n.updated_at else None,
            }
        )

    combined = (insight_payloads + node_payloads)[:limit]
    truncated = (len(insight_rows) + len(node_rows)) > limit

    citations: list[Citation] = []
    for row in combined:
        if row["source"] == "insight":
            citations.append(Citation(kind="insight", id=uuid.UUID(row["id"])))
            for nid in row.get("citation_node_ids") or []:
                citations.append(Citation(kind="node", id=uuid.UUID(nid)))
            for ev in row.get("evidence_event_ids") or []:
                citations.append(Citation(kind="event", id=uuid.UUID(ev)))
        else:
            citations.append(Citation(kind="node", id=uuid.UUID(row["id"])))
            for ev in row.get("evidence_event_ids") or []:
                citations.append(Citation(kind="event", id=uuid.UUID(ev)))

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        await emit_tool_invocation(
            session,
            tool_name="get_open_risks",
            input_hash=hash_tool_input({"severity": severity, "limit": limit}),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len(combined),
            duration_ms=duration_ms,
            truncated=truncated,
            turn_id=turn_id,
            extra_detail={
                "insight_count": len(insight_rows),
                "node_count": len(node_rows),
                "total_returned": len(combined),
            },
        )
    return ToolResult(
        name="get_open_risks",
        rows=combined,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
    )


def _iso_to_sort_key(value: Any) -> int:
    """Best-effort numeric sort key from an ISO 8601 timestamp string.

    Used purely for stable ordering inside the in-memory severity bucket
    sort — we never compare across timezones, just sort within one bucket
    so the more-recent insight wins. Falls back to 0 on parse failure
    (effectively oldest).
    """
    if not isinstance(value, str):
        return 0
    # YYYYMMDDHHMMSS-ish — strip non-digits, take the first 14
    digits = "".join(ch for ch in value if ch.isdigit())
    if not digits:
        return 0
    try:
        return int(digits[:14])
    except ValueError:
        return 0


async def list_matrix_nodes_by_type(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_type: str,
    limit: int = _DEFAULT_LIMIT,
    turn_id: uuid.UUID | None = None,
    emit_audit: bool = True,
) -> ToolResult:
    """List matrix nodes filtered by ``node_type`` (newest first).

    Returns human-readable titles + descriptions for any node type in the
    catalog (stakeholder, decision, risk, meeting, etc). Citations come
    from each row's ``evidence_event_ids``. Custom tenant-registered node
    types are accepted at runtime even if not in
    :data:`MATRIX_NODE_TYPES` — the catalog is the *built-in* list, but
    ``tenant_node_types`` extends it.
    """
    started = time.perf_counter()
    tid, eid = _require_scope(tenant_id=tenant_id, engagement_id=engagement_id)
    if not (1 <= limit <= _MAX_LIMIT):
        raise ToolError(f"limit must be between 1 and {_MAX_LIMIT}")
    if not isinstance(node_type, str) or not node_type.strip():
        raise ToolError("node_type must be a non-empty string")
    nt = node_type.strip()

    # Soft validation: if the caller passes a built-in catalog type we
    # don't even hit the DB to check; otherwise we still query (could be a
    # tenant-custom type) and just flag ``validation_error`` so the model
    # knows it asked for something off-catalog without crashing the turn.
    validation_error: str | None = None
    if nt not in MATRIX_NODE_TYPES:
        validation_error = (
            f"node_type {nt!r} is not in the built-in catalog "
            f"({', '.join(MATRIX_NODE_TYPES)}); querying anyway in case a "
            "tenant-custom type is registered."
        )

    stmt = (
        select(MatrixNode)
        .where(
            MatrixNode.tenant_id == tid,
            MatrixNode.engagement_id == eid,
            MatrixNode.node_type == nt,
        )
        .where(
            (MatrixNode.status.is_(None)) | (MatrixNode.status != "archived"),
        )
        .order_by(MatrixNode.created_at.desc())
        .limit(limit + 1)
    )

    nodes = list((await session.execute(stmt)).scalars().all())
    truncated = len(nodes) > limit
    if truncated:
        nodes = nodes[:limit]

    rows: list[dict[str, Any]] = []
    citations: list[Citation] = []
    for n in nodes:
        row: dict[str, Any] = {
            "id": str(n.id),
            "title": n.title,
            "description": _truncate(_node_description(n)),
            "node_type": n.node_type,
            "status": n.status,
            "evidence_event_ids": [str(e) for e in (n.evidence_event_ids or [])],
            "created_at": n.created_at.isoformat() if n.created_at else None,
            "attributes": n.attributes or {},
            "citations": (
                [{"kind": "node", "id": str(n.id)}]
                + [{"kind": "event", "id": str(e)} for e in (n.evidence_event_ids or [])]
            ),
        }
        rows.append(row)
        citations.append(Citation(kind="node", id=n.id))
        for ev in n.evidence_event_ids or []:
            citations.append(Citation(kind="event", id=ev))

    if validation_error and not rows:
        # Surface as a single information row so the model can see the
        # mismatch but still gets a structured payload back. The audit
        # row also records the validation_error.
        rows = [
            {
                "validation_error": validation_error,
                "requested_node_type": nt,
                "supported_node_types": list(MATRIX_NODE_TYPES),
            }
        ]

    duration_ms = (time.perf_counter() - started) * 1000.0
    if emit_audit:
        extra: dict[str, Any] = {
            "node_type": nt,
            "returned": len([r for r in rows if "validation_error" not in r]),
        }
        if validation_error is not None:
            extra["validation_error"] = validation_error
        await emit_tool_invocation(
            session,
            tool_name="list_matrix_nodes_by_type",
            input_hash=hash_tool_input({"node_type": nt, "limit": limit}),
            tenant_id=tid,
            engagement_id=eid,
            row_count=len([r for r in rows if "validation_error" not in r]),
            duration_ms=duration_ms,
            truncated=truncated,
            turn_id=turn_id,
            extra_detail=extra,
        )
    return ToolResult(
        name="list_matrix_nodes_by_type",
        rows=rows,
        citations=citations,
        truncated=truncated,
        next_cursor=None,
        duration_ms=duration_ms,
        detail=validation_error,
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
        description=(
            "Returns open risk insights (compounded synthesis from matrix_insights) "
            "AND raw risk-type matrix nodes. Each row carries source=insight|node, "
            "title, description (truncated), severity (insights only), and "
            "evidence_event_ids citations. Use this for human-readable risk triage "
            "even when the synthesis layer has not yet run."
        ),
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
register_tool(
    ToolSpec(
        name="list_matrix_nodes_by_type",
        description=(
            "List matrix nodes filtered by type (stakeholder, decision, risk, "
            "meeting, etc). Returns titles and descriptions for human-readable "
            "triage. Citations come from each node's evidence_event_ids."
        ),
        input_schema=LIST_MATRIX_NODES_BY_TYPE_INPUT_SCHEMA,
    )
)


__all__ = [
    "GET_DECISION_HISTORY_INPUT_SCHEMA",
    "GET_ENGAGEMENT_SUMMARY_INPUT_SCHEMA",
    "GET_OPEN_RISKS_INPUT_SCHEMA",
    "LIST_MATRIX_NODES_BY_TYPE_INPUT_SCHEMA",
    "get_decision_history",
    "get_engagement_summary",
    "get_open_risks",
    "list_matrix_nodes_by_type",
]
