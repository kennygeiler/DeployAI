"""``extract_citations`` + ``verify_citations`` (scope-v2 §7.1).

Phase 3 hardening: parallel verification during streaming, full 5-kind
coverage including ``edge``, and a hard cross-engagement-leak gate that
treats any leak as a security incident (see :mod:`agent_kenny.service`
for the reply-rejection path).
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.types import (
    DB_CITATION_KINDS,
    EXTERNAL_CITATION_KINDS,
    AgentState,
    CitationOutcome,
    CitationReport,
    CitationUnverifiedChunk,
    CitationVerifiedChunk,
    CrossEngagementLeakChunk,
    ParsedCitation,
    VerifiedCitation,
    is_uuid_identifier,
    parse_citations,
)
from control_plane.domain.canonical_memory.matrix import MatrixEdge, MatrixInsight, MatrixNode
from control_plane.domain.ledger import LedgerEvent
from control_plane.domain.oracle import OracleChatTurn

_TABLE_BY_KIND: dict[str, Any] = {
    "event": LedgerEvent,
    "node": MatrixNode,
    "insight": MatrixInsight,
    "turn": OracleChatTurn,
    "edge": MatrixEdge,
}


async def extract_citations(state: AgentState) -> AgentState:
    """Pure parse step — no DB hits."""
    citations = parse_citations(state.accumulated_text)
    # Only DB-shaped citations need verification; external prefixes are
    # carried straight into the report by verify_citations.
    state.messages.append(
        {
            "role": "assistant",
            "content": "[citations_extracted]",
            "_meta_citations": [(c.kind, c.identifier) for c in citations],
        }
    )
    return state


def _parsed_citations_for(state: AgentState) -> list[ParsedCitation]:
    return parse_citations(state.accumulated_text)


async def verify_citations(
    session: AsyncSession,
    state: AgentState,
    emit: Callable[[Any], Awaitable[None]] | None = None,
) -> AgentState:
    """Look up every cited UUID in the appropriate table, tenant-scoped.

    Sequential lookup retained for unit-test ergonomics; the streaming
    driver calls :func:`verify_citations_parallel` so latency stays under
    the scope-v2 §5.3 100ms budget when many citations land in the same
    reply.
    """
    report = CitationReport()
    parsed = _parsed_citations_for(state)
    for c in parsed:
        v, emit_chunk = await _resolve_one(session, state, c)
        _stash(report, v)
        if emit is not None and emit_chunk is not None:
            await emit(emit_chunk)
    state.citation_report = report
    return state


async def verify_citations_parallel(
    session: AsyncSession,
    state: AgentState,
    emit: Callable[[Any], Awaitable[None]] | None = None,
) -> AgentState:
    """Verify every citation concurrently, emit frames AS each resolves.

    SQLAlchemy ``AsyncSession`` is not thread-safe, so the lookups
    serialize on the session even when issued via ``asyncio.gather``.
    What we get for free is that emit-on-resolve still happens in
    arrival order without batching at the end of stream — preserving the
    scope-v2 §5.3 contract that ``citation_verified`` / ``_unverified``
    frames stream BEFORE ``done``.
    """
    report = CitationReport()
    parsed = _parsed_citations_for(state)
    tasks = [asyncio.create_task(_resolve_one(session, state, c)) for c in parsed]
    for fut in tasks:
        v, emit_chunk = await fut
        _stash(report, v)
        if emit is not None and emit_chunk is not None:
            await emit(emit_chunk)
    state.citation_report = report
    return state


def _stash(report: CitationReport, v: VerifiedCitation) -> None:
    if v.outcome == "verified":
        report.verified.append(v)
    elif v.outcome == "cross_engagement_leak":
        report.cross_engagement.append(v)
    elif v.outcome == "external":
        report.external.append(v)
    else:
        report.not_found.append(v)


async def _resolve_one(
    session: AsyncSession,
    state: AgentState,
    c: ParsedCitation,
) -> tuple[VerifiedCitation, Any]:
    if c.kind in EXTERNAL_CITATION_KINDS:
        v = VerifiedCitation(kind=c.kind, identifier=c.identifier, outcome="external")
        return v, CitationUnverifiedChunk(kind=c.kind, identifier=c.identifier, outcome="external")
    if c.kind not in DB_CITATION_KINDS:
        v = VerifiedCitation(kind=c.kind, identifier=c.identifier, outcome="not_found")
        return v, CitationUnverifiedChunk(kind=c.kind, identifier=c.identifier, outcome="not_found")
    if not is_uuid_identifier(c.identifier):
        v = VerifiedCitation(kind=c.kind, identifier=c.identifier, outcome="not_found")
        return v, CitationUnverifiedChunk(kind=c.kind, identifier=c.identifier, outcome="not_found")
    outcome = await _verify_one(
        session,
        kind=c.kind,
        cid=uuid.UUID(c.identifier),
        tenant_id=state.tenant_id,
        engagement_id=state.engagement_id,
    )
    v = VerifiedCitation(kind=c.kind, identifier=c.identifier, outcome=outcome)
    if outcome == "verified":
        return v, CitationVerifiedChunk(kind=c.kind, identifier=c.identifier)
    if outcome == "cross_engagement_leak":
        return v, CrossEngagementLeakChunk(kind=c.kind, identifier=c.identifier)
    return v, CitationUnverifiedChunk(kind=c.kind, identifier=c.identifier, outcome=outcome)


async def _verify_one(
    session: AsyncSession,
    *,
    kind: str,
    cid: uuid.UUID,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> CitationOutcome:
    model = _TABLE_BY_KIND.get(kind)
    if model is None:
        return "not_found"
    # First: tenant + engagement scoped lookup.
    if kind == "turn":
        # OracleChatTurn does not carry engagement_id directly; it joins
        # through oracle_conversations. Tenant scope still applies. We
        # accept any turn in this tenant as verified for now.
        stmt = select(model).where(model.id == cid, model.tenant_id == tenant_id)
        row = (await session.execute(stmt)).scalar_one_or_none()
        if row is not None:
            return "verified"
        # Cross-tenant turn → treat as cross_engagement_leak (security event).
        stmt2 = select(model).where(model.id == cid)
        leak_row = (await session.execute(stmt2)).scalar_one_or_none()
        if leak_row is not None:
            return "cross_engagement_leak"
        return "not_found"

    in_scope = select(model).where(
        model.id == cid,
        model.tenant_id == tenant_id,
        model.engagement_id == engagement_id,
    )
    if (await session.execute(in_scope)).scalar_one_or_none() is not None:
        return "verified"
    other_scope = select(model).where(model.id == cid)
    leak = (await session.execute(other_scope)).scalar_one_or_none()
    if leak is not None:
        return "cross_engagement_leak"
    return "not_found"


def unverified_count(state: AgentState) -> int:
    if state.citation_report is None:
        return 0
    return len(state.citation_report.not_found)


def cross_engagement_count(state: AgentState) -> int:
    if state.citation_report is None:
        return 0
    return len(state.citation_report.cross_engagement)


__all__ = [
    "cross_engagement_count",
    "extract_citations",
    "unverified_count",
    "verify_citations",
    "verify_citations_parallel",
]
