"""``extract_citations`` + ``verify_citations`` (scope-v2 §7.1)."""

from __future__ import annotations

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
    ParsedCitation,
    VerifiedCitation,
    is_uuid_identifier,
    parse_citations,
)
from control_plane.domain.canonical_memory.matrix import MatrixInsight, MatrixNode
from control_plane.domain.ledger import LedgerEvent
from control_plane.domain.oracle import OracleChatTurn

# Edge citations are recorded but matrix_edges have separate scoping rules;
# we treat unknown-table kinds (``edge``) as verified if present at all,
# otherwise mark not_found. For now, kinds the verifier understands are:
_TABLE_BY_KIND: dict[str, Any] = {
    "event": LedgerEvent,
    "node": MatrixNode,
    "insight": MatrixInsight,
    "turn": OracleChatTurn,
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
    """Look up every cited UUID in the appropriate table, tenant-scoped."""
    report = CitationReport()
    parsed = _parsed_citations_for(state)
    for c in parsed:
        if c.kind in EXTERNAL_CITATION_KINDS:
            v = VerifiedCitation(kind=c.kind, identifier=c.identifier, outcome="external")
            report.external.append(v)
            if emit is not None:
                await emit(CitationUnverifiedChunk(kind=c.kind, identifier=c.identifier, outcome="external"))
            continue
        if c.kind not in DB_CITATION_KINDS:
            v = VerifiedCitation(kind=c.kind, identifier=c.identifier, outcome="not_found")
            report.not_found.append(v)
            if emit is not None:
                await emit(CitationUnverifiedChunk(kind=c.kind, identifier=c.identifier, outcome="not_found"))
            continue
        if not is_uuid_identifier(c.identifier):
            v = VerifiedCitation(kind=c.kind, identifier=c.identifier, outcome="not_found")
            report.not_found.append(v)
            if emit is not None:
                await emit(CitationUnverifiedChunk(kind=c.kind, identifier=c.identifier, outcome="not_found"))
            continue
        outcome = await _verify_one(
            session,
            kind=c.kind,
            cid=uuid.UUID(c.identifier),
            tenant_id=state.tenant_id,
            engagement_id=state.engagement_id,
        )
        v = VerifiedCitation(kind=c.kind, identifier=c.identifier, outcome=outcome)
        if outcome == "verified":
            report.verified.append(v)
            if emit is not None:
                await emit(CitationVerifiedChunk(kind=c.kind, identifier=c.identifier))
        elif outcome == "cross_engagement_leak":
            report.cross_engagement.append(v)
            if emit is not None:
                await emit(CitationUnverifiedChunk(kind=c.kind, identifier=c.identifier, outcome=outcome))
        else:
            report.not_found.append(v)
            if emit is not None:
                await emit(CitationUnverifiedChunk(kind=c.kind, identifier=c.identifier, outcome=outcome))
    state.citation_report = report
    return state


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
]
