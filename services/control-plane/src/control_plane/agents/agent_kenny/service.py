"""KennyAgentService — drives the Phase 2 LangGraph loop (scope-v2 §6).

Public surface: :meth:`reply_stream` returns an async iterator of
:class:`StreamChunk` instances. The route layer wraps each chunk in an
SSE frame and writes it to the client.

This driver walks the same nodes the LangGraph topology declares (see
``graph.py``), but does so imperatively so the live ``AsyncSession`` and
emit sink can travel through. A future Phase 3 / Phase 6 refactor may
swap this for native LangGraph execution if checkpointed replay becomes
necessary.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from llm_provider_py.types import LLMProvider
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.budget import charge_turn
from control_plane.agents.agent_kenny.graph import (
    build_graph,
    has_tool_calls_router,
    unverified_router,
)
from control_plane.agents.agent_kenny.nodes.adversarial import adversarial_review
from control_plane.agents.agent_kenny.nodes.citations import (
    extract_citations,
    verify_citations,
)
from control_plane.agents.agent_kenny.nodes.llm_call import call_llm_with_tools
from control_plane.agents.agent_kenny.nodes.persist import (
    _ConversationNotFound,
    get_or_create_conversation,
    persist_turn,
)
from control_plane.agents.agent_kenny.nodes.retrieve import retrieve_initial_context
from control_plane.agents.agent_kenny.nodes.revise import revise_if_unverified
from control_plane.agents.agent_kenny.nodes.tool_dispatch import dispatch_tools
from control_plane.agents.agent_kenny.types import (
    MAX_TOOL_CALLS_PER_TURN,
    TURN_HARD_TIMEOUT_S,
    AgentState,
    BudgetExhaustedError,
    ConversationNotFoundError,
    CrossEngagementLeakError,
    DoneChunk,
    ErrorChunk,
    StreamChunk,
)
from control_plane.ledger import emit_ledger_event

_log = logging.getLogger(__name__)

_SECURITY_REJECT_REPLY = "I'm unable to answer that question."


class KennyAgentService:
    """Compose one Agent Kenny v2 turn via the LangGraph loop."""

    def __init__(
        self,
        provider: LLMProvider,
        cheap_provider: LLMProvider | None = None,
    ) -> None:
        self._provider = provider
        self._cheap = cheap_provider or provider
        self._graph = build_graph()

    async def reply_stream(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message: str,
        now: datetime | None = None,
    ) -> AsyncIterator[StreamChunk]:
        """Pre-flight (budget + conversation) runs eagerly; the rest streams lazily."""
        moment = now or datetime.now(UTC)

        if conversation_id is not None:
            existing = await session.get(
                __import__("control_plane.domain.oracle", fromlist=["OracleConversation"]).OracleConversation,
                conversation_id,
            )
            if existing is None or existing.tenant_id != tenant_id or existing.engagement_id != engagement_id:
                raise ConversationNotFoundError

        granted = await charge_turn(session, tenant_id=tenant_id)
        if not granted:
            raise BudgetExhaustedError

        return self._drive(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            actor_user_id=actor_user_id,
            conversation_id=conversation_id,
            message=message,
            moment=moment,
        )

    async def _drive(
        self,
        session: AsyncSession,
        *,
        tenant_id: uuid.UUID,
        engagement_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        message: str,
        moment: datetime,
    ) -> AsyncIterator[StreamChunk]:
        queue: asyncio.Queue[StreamChunk] = asyncio.Queue()
        sentinel: Any = object()

        async def emit(chunk: Any) -> None:
            await queue.put(chunk)

        state = AgentState(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            actor_user_id=actor_user_id,
            conversation_id=conversation_id,
            user_message=message,
            started_at=moment,
        )

        async def runner() -> None:
            try:
                await asyncio.wait_for(
                    self._run_graph(
                        session,
                        state,
                        actor_user_id=actor_user_id,
                        conversation_id=conversation_id,
                        moment=moment,
                        emit=emit,
                    ),
                    timeout=TURN_HARD_TIMEOUT_S,
                )
            except CrossEngagementLeakError as exc:
                _log.warning("kenny v2 cross-engagement leak: %s", exc)
                await emit(ErrorChunk(error="cross_engagement_leak"))
            except TimeoutError:
                await emit(ErrorChunk(error="turn_timeout"))
                state.error = "turn_timeout"
            except Exception as exc:
                _log.exception("kenny v2 graph error")
                await emit(ErrorChunk(error=str(exc)[:200]))
                state.error = str(exc)[:200]
            finally:
                await queue.put(sentinel)

        task = asyncio.create_task(runner())
        try:
            while True:
                chunk = await queue.get()
                if chunk is sentinel:
                    break
                yield chunk
            await task
        finally:
            if not task.done():
                task.cancel()

    async def _run_graph(
        self,
        session: AsyncSession,
        state: AgentState,
        *,
        actor_user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        moment: datetime,
        emit: Any,
    ) -> None:
        # 1. retrieve
        await retrieve_initial_context(session, state)

        # 2. main loop: llm_call -> dispatch_tools -> llm_call ...
        await call_llm_with_tools(self._provider, state, emit=emit)
        while has_tool_calls_router(state) == "dispatch_tools" and state.tool_calls_made < MAX_TOOL_CALLS_PER_TURN:
            await dispatch_tools(session, state, emit=emit, turn_id_hint=None)
            await call_llm_with_tools(self._provider, state, emit=emit)
            # Guard: an LLM that keeps proposing tool calls past the cap
            # should be forced to stop with the budget exhausted.
            if state.tool_calls_made >= MAX_TOOL_CALLS_PER_TURN:
                # Drain any remaining pending intents to ensure a final reply.
                if state.pending_tool_calls:
                    state.pending_tool_calls = []
                if not state.accumulated_text:
                    state.accumulated_text = (
                        state.last_text.replace("<tool_call>", "").replace("</tool_call>", "").strip()
                        or "(tool-call cap reached)"
                    )
                break

        # 3. citations + revision loop
        for _ in range(3):  # at most 1 initial + 2 revisions
            await extract_citations(state)
            await verify_citations(session, state, emit=emit)
            route = unverified_router(state)
            if route == "revise":
                await revise_if_unverified(self._provider, state, emit=emit)
                continue
            break

        # 4. Security gate: cross-engagement leak overrides everything.
        if state.citation_report is not None and state.citation_report.cross_engagement:
            state.security_rejected = True
            leak_count = len(state.citation_report.cross_engagement)
            leak_summary = f"kenny v2 reply REJECTED — cited {leak_count} cross-engagement id(s)"
            await emit_ledger_event(
                session,
                tenant_id=state.tenant_id,
                engagement_id=state.engagement_id,
                occurred_at=moment,
                actor_kind="agent:kenny",
                actor_id=str(actor_user_id),
                source_kind="agent_cross_engagement_leak",
                source_ref=None,
                summary=leak_summary[:500],
                detail={
                    "actor_user_id": str(actor_user_id),
                    "leaked_citations": [
                        {"kind": c.kind, "id": c.identifier} for c in state.citation_report.cross_engagement
                    ],
                    "user_message": state.user_message[:500],
                },
            )
            state.accumulated_text = _SECURITY_REJECT_REPLY
            state.final_text = _SECURITY_REJECT_REPLY
            # Persist a stripped reply so the audit trail still shows the turn.
            try:
                convo, started_new = await get_or_create_conversation(
                    session,
                    tenant_id=state.tenant_id,
                    engagement_id=state.engagement_id,
                    actor_user_id=actor_user_id,
                    conversation_id=conversation_id,
                )
            except _ConversationNotFound as exc:
                raise ConversationNotFoundError from exc
            await persist_turn(
                session,
                state,
                conversation=convo,
                conversation_started_new=started_new,
                moment=moment,
            )
            assert state.final_turn_id is not None
            assert state.final_conversation_id is not None
            await emit(
                DoneChunk(
                    turn_id=state.final_turn_id,
                    conversation_id=state.final_conversation_id,
                    tokens=state.final_tokens,
                    tool_calls=state.tool_calls_made,
                    revision_attempts=state.revision_attempts,
                    adversarial_concerns=len(state.adversarial_concerns),
                    final_text=state.final_text,
                )
            )
            return

        # 5. adversarial review
        try:
            await adversarial_review(self._cheap, state)
        except Exception as exc:
            _log.warning("kenny v2 adversarial review failed: %s", exc)
            state.adversarial_concerns = []

        # 6. persist + done
        try:
            convo, started_new = await get_or_create_conversation(
                session,
                tenant_id=state.tenant_id,
                engagement_id=state.engagement_id,
                actor_user_id=actor_user_id,
                conversation_id=conversation_id,
            )
        except _ConversationNotFound as exc:
            raise ConversationNotFoundError from exc

        if not state.final_text:
            state.final_text = state.accumulated_text or "(no response)"

        await persist_turn(
            session,
            state,
            conversation=convo,
            conversation_started_new=started_new,
            moment=moment,
        )

        assert state.final_turn_id is not None
        assert state.final_conversation_id is not None
        await emit(
            DoneChunk(
                turn_id=state.final_turn_id,
                conversation_id=state.final_conversation_id,
                tokens=state.final_tokens,
                tool_calls=state.tool_calls_made,
                revision_attempts=state.revision_attempts,
                adversarial_concerns=len(state.adversarial_concerns),
                final_text=state.final_text,
            )
        )


__all__ = ["KennyAgentService"]
