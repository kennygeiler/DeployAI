"""Internal API — Agent Kenny telemetry dashboard aggregate (Phase 6 Wave C).

Mounted under ``/internal/v1``. Returns one aggregate JSON document the
strategist admin "Agent Kenny dashboard" page renders. Scope-v2 §11.4.

All inputs are read-only aggregations over data that already lands on the
production write paths:

* ``agent_audit_traces`` — one row per Kenny v2 turn (citation counts,
  latency, tool-call count, adversarial concerns, final reply text).
* ``ledger_events`` filtered to ``agent_tool_invocation`` — per-tool
  call counts (the audit-trace row has the *total* count for the turn
  but not the per-tool breakdown; that lives in the ledger detail blob).
* ``ledger_events`` filtered to ``oracle_chat_turn`` joined with
  ``ledger_event_causes`` — top events Kenny cites most often
  (``caused_by_id`` on the oracle turn points at the event the agent
  pulled into the conversation).
* ``lint_flags`` — open + recently-resolved integrity flags by kind.

No new schema, no new write path. The route is one tenant's slice (the
admin page is per-tenant via the BFF guard).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.api.routes.tenants_internal import _require_tenant
from control_plane.db import get_app_db_session
from control_plane.domain.canonical_memory.agent_audit import AgentAuditTrace
from control_plane.domain.ledger import LedgerEvent, LedgerEventCause
from control_plane.domain.lint import LintFlag

router = APIRouter(prefix="/tenants", tags=["internal-agent-kenny-dashboard"])

_WINDOW_MIN = 1
_WINDOW_MAX = 90
_WINDOW_DEFAULT = 7

# Tokens we treat as "Kenny said it doesn't know". Lower-cased contains
# match — keeps the SQL portable (no full-text index needed) and aligns
# with the prompt instruction "If you don't know, say so" (see
# ``services/.../agent_kenny/nodes/llm_call.py`` and ``oracle_chat.py``).
_IDK_NEEDLES: tuple[str, ...] = ("i don't know", "i do not know")

_TOP_TOOL_LIMIT = 10
_TOP_CITED_EVENT_LIMIT = 10
_LINT_KIND_LIMIT = 20
# Cap the summary preview so the JSON stays compact even when the agent
# pulls in long event summaries (the column itself is capped at 500 by
# the ``ledger_summary_len`` CHECK).
_SUMMARY_PREVIEW_LEN = 200


class ToolCallCount(BaseModel):
    tool: str
    count: int


class LintFlagCount(BaseModel):
    kind: str
    count: int
    most_recent: datetime | None = None


class TopCitedEvent(BaseModel):
    event_id: uuid.UUID
    summary: str
    citation_count: int


class AgentKennyDashboardResponse(BaseModel):
    window_days: int = Field(..., ge=_WINDOW_MIN, le=_WINDOW_MAX)
    hallucination_rate: float
    citations_total: int
    citations_unverified: int
    latency_p50_ms: int
    latency_p95_ms: int
    latency_p99_ms: int
    idk_rate: float
    tool_calls: list[ToolCallCount]
    lint_flag_counts: list[LintFlagCount]
    top_cited_events: list[TopCitedEvent]
    adversarial_concerns_total: int


@router.get(
    "/{tenant_id}/agent_kenny_dashboard",
    response_model=AgentKennyDashboardResponse,
    dependencies=[Depends(require_internal)],
)
async def get_agent_kenny_dashboard(
    tenant_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    window_days: Annotated[int, Query(ge=_WINDOW_MIN, le=_WINDOW_MAX)] = _WINDOW_DEFAULT,
) -> AgentKennyDashboardResponse:
    """One aggregate document scoped to ``tenant_id`` over the last ``window_days``.

    Empty windows return zeros (no rows = no signal). All percentiles use
    Postgres ``percentile_cont`` so the values are interpolated, not bucketed.
    """
    await _require_tenant(session, tenant_id)

    now = datetime.now(UTC)
    window_start = now - timedelta(days=window_days)

    audit_aggregates = await _audit_aggregates(session, tenant_id, window_start)
    tool_calls = await _tool_call_counts(session, tenant_id, window_start)
    lint_counts = await _lint_flag_counts(session, tenant_id, window_start)
    top_cited = await _top_cited_events(session, tenant_id, window_start)

    return AgentKennyDashboardResponse(
        window_days=window_days,
        hallucination_rate=audit_aggregates["hallucination_rate"],
        citations_total=audit_aggregates["citations_total"],
        citations_unverified=audit_aggregates["citations_unverified"],
        latency_p50_ms=audit_aggregates["latency_p50_ms"],
        latency_p95_ms=audit_aggregates["latency_p95_ms"],
        latency_p99_ms=audit_aggregates["latency_p99_ms"],
        idk_rate=audit_aggregates["idk_rate"],
        tool_calls=tool_calls,
        lint_flag_counts=lint_counts,
        top_cited_events=top_cited,
        adversarial_concerns_total=audit_aggregates["adversarial_concerns_total"],
    )


async def _audit_aggregates(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    window_start: datetime,
) -> dict[str, float | int]:
    """Aggregate ``agent_audit_traces`` for the dashboard's headline numbers.

    Returns zeros for an empty window — divisions guard against
    zero-denominator. ``percentile_cont`` over an empty set is ``NULL``;
    we coerce to 0 so the response shape stays integer-friendly.
    """
    # IDK rate uses a SQL-level case-insensitive substring search so we
    # don't have to pull every final_text back into Python.
    idk_predicate = or_(*[func.lower(AgentAuditTrace.final_text).contains(needle) for needle in _IDK_NEEDLES])

    stmt = select(
        func.coalesce(func.sum(AgentAuditTrace.total_citations), 0),
        func.coalesce(func.sum(AgentAuditTrace.unverified_count), 0),
        func.coalesce(func.sum(AgentAuditTrace.adversarial_concerns_count), 0),
        func.count(AgentAuditTrace.id),
        func.coalesce(func.count().filter(idk_predicate), 0),
        func.percentile_cont(0.5).within_group(AgentAuditTrace.duration_ms.asc()),
        func.percentile_cont(0.95).within_group(AgentAuditTrace.duration_ms.asc()),
        func.percentile_cont(0.99).within_group(AgentAuditTrace.duration_ms.asc()),
    ).where(
        AgentAuditTrace.tenant_id == tenant_id,
        AgentAuditTrace.created_at >= window_start,
    )

    row = (await session.execute(stmt)).one()
    total_citations = int(row[0] or 0)
    unverified = int(row[1] or 0)
    concerns_total = int(row[2] or 0)
    turns_total = int(row[3] or 0)
    idk_turns = int(row[4] or 0)
    p50 = float(row[5] or 0.0)
    p95 = float(row[6] or 0.0)
    p99 = float(row[7] or 0.0)

    hallucination_rate = (unverified / total_citations) if total_citations > 0 else 0.0
    idk_rate = (idk_turns / turns_total) if turns_total > 0 else 0.0

    return {
        "hallucination_rate": round(hallucination_rate, 4),
        "citations_total": total_citations,
        "citations_unverified": unverified,
        "latency_p50_ms": round(p50),
        "latency_p95_ms": round(p95),
        "latency_p99_ms": round(p99),
        "idk_rate": round(idk_rate, 4),
        "adversarial_concerns_total": concerns_total,
    }


async def _tool_call_counts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    window_start: datetime,
) -> list[ToolCallCount]:
    """Top-N tools by invocation count from ``agent_tool_invocation`` ledger rows.

    The audit-trace ``tool_calls_count`` is a per-turn total only; the
    per-tool breakdown lives in the JSONB ``detail.tool_name`` written
    by ``agents/tools/audit.py``. Filtering by ``source_kind`` first
    uses ``ix_ledger_source_kind``; the JSONB extract is cheap because
    the GIN index on ``detail`` short-circuits the missing-key case.
    """
    tool_name = LedgerEvent.detail["tool_name"].astext.label("tool_name")
    stmt = (
        select(tool_name, func.count(LedgerEvent.id).label("call_count"))
        .where(
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.source_kind == "agent_tool_invocation",
            LedgerEvent.occurred_at >= window_start,
            LedgerEvent.detail["tool_name"].astext.is_not(None),
        )
        .group_by(tool_name)
        .order_by(desc("call_count"), tool_name.asc())
        .limit(_TOP_TOOL_LIMIT)
    )
    rows = (await session.execute(stmt)).all()
    return [ToolCallCount(tool=str(name), count=int(count)) for name, count in rows]


async def _lint_flag_counts(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    window_start: datetime,
) -> list[LintFlagCount]:
    """Open + recently-flagged ``lint_flags`` grouped by ``kind``.

    "Recently flagged" = flagged inside the window. We DO include
    already-resolved flags because the dashboard is a substrate-health
    view; a flag raised then resolved still counts as substrate friction
    Kenny had to surface.
    """
    stmt = (
        select(
            LintFlag.kind,
            func.count(LintFlag.id).label("count"),
            func.max(LintFlag.flagged_at).label("most_recent"),
        )
        .where(
            LintFlag.tenant_id == tenant_id,
            LintFlag.flagged_at >= window_start,
        )
        .group_by(LintFlag.kind)
        .order_by(desc("count"), LintFlag.kind.asc())
        .limit(_LINT_KIND_LIMIT)
    )
    rows = (await session.execute(stmt)).all()
    return [
        LintFlagCount(kind=str(kind), count=int(count), most_recent=most_recent) for kind, count, most_recent in rows
    ]


async def _top_cited_events(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    window_start: datetime,
) -> list[TopCitedEvent]:
    """Events Kenny cited most often inside the window.

    We treat ``ledger_event_causes`` edges that point *from* an
    ``oracle_chat_turn`` row to another ledger event (the "caused_by"
    side) as the canonical record of "Kenny referenced this event". The
    ``persist_turn`` node stamps these for every event id that came
    through ``initial_context.recent_ledger`` — and the citation
    verifier adds DB-shaped citations the same way via the verified
    event ids in scope-v2 §7.1. The audit page renders ``summary``
    truncated to ``_SUMMARY_PREVIEW_LEN``.
    """
    turn_alias = LedgerEvent.__table__.alias("turn")
    cited_alias = LedgerEvent.__table__.alias("cited")

    stmt = (
        select(
            cited_alias.c.id,
            cited_alias.c.summary,
            func.count(LedgerEventCause.caused_by_id).label("citation_count"),
        )
        .select_from(
            turn_alias.join(
                LedgerEventCause.__table__,
                LedgerEventCause.event_id == turn_alias.c.id,
            ).join(
                cited_alias,
                cited_alias.c.id == LedgerEventCause.caused_by_id,
            )
        )
        .where(
            turn_alias.c.tenant_id == tenant_id,
            turn_alias.c.source_kind == "oracle_chat_turn",
            turn_alias.c.occurred_at >= window_start,
            cited_alias.c.tenant_id == tenant_id,
        )
        .group_by(cited_alias.c.id, cited_alias.c.summary)
        .order_by(desc("citation_count"), cited_alias.c.id.asc())
        .limit(_TOP_CITED_EVENT_LIMIT)
    )
    rows = (await session.execute(stmt)).all()
    return [
        TopCitedEvent(
            event_id=event_id,
            summary=_truncate_summary(summary),
            citation_count=int(count),
        )
        for event_id, summary, count in rows
    ]


def _truncate_summary(text: str | None) -> str:
    """Shorten an event summary to ``_SUMMARY_PREVIEW_LEN`` for the dashboard."""
    if not text:
        return ""
    if len(text) <= _SUMMARY_PREVIEW_LEN:
        return text
    return text[: _SUMMARY_PREVIEW_LEN - 1].rstrip() + "…"


__all__ = ["router"]
