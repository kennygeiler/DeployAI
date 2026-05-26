"""``persist_turn`` — INSERT user + oracle turns + audit trace + ledger event.

Caller commits the transaction; the node only adds rows + flushes so a
rollback drops the entire turn atomically.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.budget import AGENT_KENNY_V2_TURN_ESTIMATE
from control_plane.agents.agent_kenny.types import AgentState
from control_plane.domain.canonical_memory.agent_audit import AgentAuditTrace
from control_plane.domain.oracle import OracleChatTurn, OracleConversation
from control_plane.ledger import emit_ledger_event


async def get_or_create_conversation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    conversation_id: uuid.UUID | None,
) -> tuple[OracleConversation, bool]:
    if conversation_id is not None:
        existing = await session.get(OracleConversation, conversation_id)
        if existing is None or existing.tenant_id != tenant_id or existing.engagement_id != engagement_id:
            raise _ConversationNotFoundError
        return existing, False
    existing_for_actor = (
        await session.execute(
            select(OracleConversation).where(
                OracleConversation.tenant_id == tenant_id,
                OracleConversation.engagement_id == engagement_id,
                OracleConversation.actor_user_id == actor_user_id,
            )
        )
    ).scalar_one_or_none()
    if existing_for_actor is not None:
        return existing_for_actor, False
    convo = OracleConversation(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        actor_user_id=actor_user_id,
    )
    session.add(convo)
    await session.flush()
    return convo, True


class _ConversationNotFoundError(Exception):
    """Internal sentinel re-raised by the service as ConversationNotFoundError."""


# Public alias retained for the service layer + tests.
_ConversationNotFound = _ConversationNotFoundError


async def persist_turn(
    session: AsyncSession,
    state: AgentState,
    *,
    conversation: OracleConversation,
    conversation_started_new: bool,
    moment: datetime,
) -> AgentState:
    """Append user + oracle turns + an audit trace row + the ledger event."""
    if conversation_started_new:
        await emit_ledger_event(
            session,
            tenant_id=state.tenant_id,
            engagement_id=state.engagement_id,
            occurred_at=moment,
            actor_kind="user",
            actor_id=str(state.actor_user_id),
            source_kind="oracle_conversation_started",
            source_ref=conversation.id,
            summary=f"oracle conversation started by user {state.actor_user_id}"[:500],
            detail={"conversation_id": str(conversation.id)},
        )

    context_event_ids: list[uuid.UUID] = []
    for r in (state.initial_context.get("recent_ledger") or [])[:20]:
        try:
            context_event_ids.append(uuid.UUID(str(r.get("id"))))
        except (TypeError, ValueError):
            continue

    user_turn = OracleChatTurn(
        conversation_id=conversation.id,
        tenant_id=state.tenant_id,
        role="user",
        content=state.user_message,
        context_event_ids=list(context_event_ids),
        tokens_used=0,
    )
    session.add(user_turn)
    await session.flush()

    tokens_used = max(state.final_tokens, AGENT_KENNY_V2_TURN_ESTIMATE)
    oracle_turn = OracleChatTurn(
        conversation_id=conversation.id,
        tenant_id=state.tenant_id,
        role="oracle",
        content=state.final_text or state.accumulated_text,
        context_event_ids=list(context_event_ids),
        tokens_used=tokens_used,
    )
    session.add(oracle_turn)
    conversation.last_turn_at = moment
    await session.flush()

    report = state.citation_report
    total_citations = report.total if report is not None else 0
    verified = len(report.verified) if report is not None else 0
    unverified = len(report.not_found) if report is not None else 0
    cross_eng = len(report.cross_engagement) if report is not None else 0
    external = len(report.external) if report is not None else 0
    duration_ms = (moment - state.started_at).total_seconds() * 1000.0

    audit = AgentAuditTrace(
        tenant_id=state.tenant_id,
        engagement_id=state.engagement_id,
        turn_id=oracle_turn.id,
        total_citations=total_citations,
        verified_count=verified,
        unverified_count=unverified,
        cross_engagement_count=cross_eng,
        external_count=external,
        revision_attempts=state.revision_attempts,
        adversarial_concerns_count=len(state.adversarial_concerns),
        tool_calls_count=state.tool_calls_made,
        total_tokens=tokens_used,
        duration_ms=max(0.0, duration_ms),
        final_text=oracle_turn.content,
    )
    session.add(audit)
    await session.flush()

    # Phase 5 Wave 1C: include external citations in the persisted
    # citation list so the audit trail captures *which* MCP provider was
    # cited (slack / linear / …). The agent_audit_traces table only
    # stores aggregate counts (no per-citation kind column → no CHECK
    # constraint to dodge), so the per-row detail lives in the ledger
    # event's JSONB ``detail`` column. Schema-level kind constraints, if
    # any are added, are Wave 2's problem — no migration here.
    external_citations_payload = [
        {"kind": c.kind, "external_kind": c.kind, "id": c.identifier} for c in (report.external if report else [])
    ]
    await emit_ledger_event(
        session,
        tenant_id=state.tenant_id,
        engagement_id=state.engagement_id,
        occurred_at=moment,
        actor_kind="agent:kenny",
        actor_id=str(oracle_turn.id),
        source_kind="oracle_chat_turn",
        source_ref=oracle_turn.id,
        summary=f"kenny v2 reply ({tokens_used} tokens, {state.tool_calls_made} tools)"[:500],
        detail={
            "role": "oracle",
            "tokens": tokens_used,
            "tool_calls": state.tool_calls_made,
            "revision_attempts": state.revision_attempts,
            "adversarial_concerns": len(state.adversarial_concerns),
            "total_citations": total_citations,
            "verified_count": verified,
            "unverified_count": unverified,
            "cross_engagement_count": cross_eng,
            "external_count": external,
            "external_citations": external_citations_payload,
            "agent_kenny_v2": True,
        },
        caused_by=context_event_ids,
    )

    if state.adversarial_concerns:
        await emit_ledger_event(
            session,
            tenant_id=state.tenant_id,
            engagement_id=state.engagement_id,
            occurred_at=moment,
            actor_kind="agent:kenny",
            actor_id=str(oracle_turn.id),
            source_kind="agent_audit_concern",
            source_ref=oracle_turn.id,
            summary=f"adversarial review flagged {len(state.adversarial_concerns)} concern(s)"[:500],
            detail={"concerns": state.adversarial_concerns[:10], "turn_id": str(oracle_turn.id)},
        )

    if unverified > 0:
        await emit_ledger_event(
            session,
            tenant_id=state.tenant_id,
            engagement_id=state.engagement_id,
            occurred_at=moment,
            actor_kind="agent:kenny",
            actor_id=str(oracle_turn.id),
            source_kind="agent_hallucination_unresolved",
            source_ref=oracle_turn.id,
            summary=f"kenny v2 turn shipped with {unverified} unresolved citation(s)"[:500],
            detail={
                "turn_id": str(oracle_turn.id),
                "unverified": [{"kind": c.kind, "id": c.identifier} for c in (report.not_found if report else [])],
            },
        )

    state.final_turn_id = oracle_turn.id
    state.final_conversation_id = conversation.id
    state.final_text = oracle_turn.content
    state.final_tokens = tokens_used
    return state


__all__ = [
    "_ConversationNotFound",
    "_ConversationNotFoundError",
    "get_or_create_conversation",
    "persist_turn",
]
