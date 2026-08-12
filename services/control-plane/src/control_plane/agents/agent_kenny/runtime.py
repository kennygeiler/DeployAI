"""LangGraph execution runtime for Agent Kenny (pilot-refresh D2/D3/D4).

Makes the StateGraph in ``graph.py`` the *actual* runtime instead of a
decorative topology: the existing node functions are wrapped into
LangGraph nodes, the shared routers drive the edges, and the
``AsyncPostgresSaver`` from ``checkpointer.py`` makes turns durable so
``interrupt()`` / ``Command(resume=...)`` human-in-the-loop approvals
work across requests.

Runtime selection: ``DEPLOYAI_AGENT_RUNTIME=langgraph|legacy`` (default
``legacy``). ``KennyAgentService`` keeps its public surface and branches
internally — see ``service.py``.

Streaming: the node functions already emit the SSE v2 chunk vocabulary
through their ``emit`` sink, so this runtime threads the same sink through
as a custom stream writer instead of remapping ``astream_events``. The
frames are produced by the exact same code the legacy driver uses —
byte-identical by construction.

Guardrails, ported not rewritten:

- token-budget pre-charge stays in ``KennyAgentService.reply_stream``
  (shared pre-flight, before either runtime starts);
- the turn timeout stays as the ``asyncio.wait_for(TURN_HARD_TIMEOUT_S)``
  wrapper around the whole run (both runtimes) plus the same wrapper
  around approval resumes;
- the tool-call cap lives in state (``tool_calls_made``) and the shared
  router; :data:`GRAPH_RECURSION_LIMIT` is derived from the same caps as
  a backstop so a routing bug cannot loop the graph unbounded.

State channels: ``AgentState`` is the graph schema. ``external_tools``
(live MCP config ORM rows + tool specs) is deliberately NOT checkpointed —
it is re-derived per request/resume and injected from the
:class:`KennyRuntime` context into the nodes that read it.
"""

from __future__ import annotations

import dataclasses
import logging
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from llm_provider_py.types import LLMProvider
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.approvals import (
    approval_required_for,
    build_approval_payload,
)
from control_plane.agents.agent_kenny.checkpointer import get_checkpointer
from control_plane.agents.agent_kenny.embeddings.voyage_client import VoyageEmbedder
from control_plane.agents.agent_kenny.graph import NodeFn, build_graph
from control_plane.agents.agent_kenny.mcp_client import McpOutboundClient
from control_plane.agents.agent_kenny.nodes.adversarial import adversarial_review
from control_plane.agents.agent_kenny.nodes.citations import (
    extract_citations,
    verify_citations_parallel,
)
from control_plane.agents.agent_kenny.nodes.llm_call import call_llm_with_tools
from control_plane.agents.agent_kenny.nodes.persist import (
    _ConversationNotFound,
    get_or_create_conversation,
    persist_concern_payload,
    persist_turn,
)
from control_plane.agents.agent_kenny.nodes.retrieve import retrieve_initial_context
from control_plane.agents.agent_kenny.nodes.revise import revise_if_unverified
from control_plane.agents.agent_kenny.nodes.tool_dispatch import (
    dispatch_tools,
    enforce_tool_call_cap,
)
from control_plane.agents.agent_kenny.types import (
    MAX_REVISION_ATTEMPTS,
    MAX_TOOL_CALLS_PER_TURN,
    AdversarialConcernChunk,
    AgentState,
    ApprovalRequiredChunk,
    ConversationNotFoundError,
    DoneChunk,
    ToolResultChunk,
)
from control_plane.ledger import emit_ledger_event

_log = logging.getLogger(__name__)

_SECURITY_REJECT_REPLY = "I'm unable to answer that question."

AGENT_RUNTIME_ENV = "DEPLOYAI_AGENT_RUNTIME"
RUNTIME_LANGGRAPH = "langgraph"
RUNTIME_LEGACY = "legacy"

# Worst-case supersteps per turn: retrieve + the llm/dispatch loop capped by
# the tool budget + the extract/verify/revise loop capped by the revision
# budget + adversarial + persist, with headroom. Purely a backstop — the
# state-carried caps terminate the loops well before this.
GRAPH_RECURSION_LIMIT = 8 + 2 * MAX_TOOL_CALLS_PER_TURN + 3 * (MAX_REVISION_ATTEMPTS + 1)

EmitFn = Callable[[Any], Awaitable[None]]

_THREAD_ID_RE = re.compile(
    r"^tenant:(?P<tenant>[0-9a-f-]{36}):engagement:(?P<engagement>[0-9a-f-]{36}):conversation:(?P<key>.+)$"
)

_STATE_FIELD_NAMES: tuple[str, ...] = tuple(f.name for f in dataclasses.fields(AgentState))
# Live ORM rows + tool specs; re-derived per request, never checkpointed.
_NON_CHECKPOINTED_CHANNELS: frozenset[str] = frozenset({"external_tools"})


def agent_runtime() -> str:
    """Resolve the runtime selector env var; unknown values fall back to legacy."""
    import os

    raw = os.environ.get(AGENT_RUNTIME_ENV, "").strip().lower()
    return RUNTIME_LANGGRAPH if raw == RUNTIME_LANGGRAPH else RUNTIME_LEGACY


def build_thread_id(tenant_id: uuid.UUID, engagement_id: uuid.UUID, conversation_key: str) -> str:
    """Tenant-scoped LangGraph thread id (pilot-refresh D1 thread-key rule)."""
    return f"tenant:{tenant_id}:engagement:{engagement_id}:conversation:{conversation_key}"


def parse_thread_id(thread_id: str) -> tuple[uuid.UUID, uuid.UUID, str] | None:
    """Recover (tenant_id, engagement_id, conversation_key), or None if malformed."""
    m = _THREAD_ID_RE.match(thread_id)
    if m is None:
        return None
    try:
        return uuid.UUID(m.group("tenant")), uuid.UUID(m.group("engagement")), m.group("key")
    except ValueError:
        return None


class ApprovalNotPendingError(Exception):
    """The thread has no interrupted run awaiting an approval decision."""


@dataclass
class KennyRuntime:
    """Per-request runtime dependencies threaded into the graph nodes.

    Everything here is request-scoped and non-serializable — the live DB
    session, the emit sink, provider handles, MCP singletons. Node
    wrappers close over this object; nothing in it touches the
    checkpointer.
    """

    session: AsyncSession
    provider: LLMProvider
    cheap_provider: LLMProvider
    emit: EmitFn
    turn_id: uuid.UUID
    moment: datetime
    actor_user_id: uuid.UUID
    conversation_id: uuid.UUID | None
    mcp_client: McpOutboundClient | None = None
    embedder: VoyageEmbedder | None = None
    external_tools: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class ResumeResult:
    """Outcome of one approval resume: either the turn finished or paused again."""

    status: Literal["done", "approval_required"]
    done: DoneChunk | None = None
    approval: ApprovalRequiredChunk | None = None


def _state_update(state: AgentState) -> dict[str, Any]:
    """Full-channel update from an in-place mutated state object.

    The node functions mutate ``AgentState`` in place (their pre-LangGraph
    contract); LangGraph only registers what a node *returns*, so each
    wrapper returns every checkpointable field.
    """
    return {n: getattr(state, n) for n in _STATE_FIELD_NAMES if n not in _NON_CHECKPOINTED_CHANNELS}


def make_node_wrappers(ctx: KennyRuntime) -> dict[str, NodeFn]:
    """Wrap the existing node functions into LangGraph node callables."""

    async def _retrieve(state: AgentState) -> dict[str, Any]:
        await retrieve_initial_context(ctx.session, state)
        return _state_update(state)

    async def _llm_call(state: AgentState) -> dict[str, Any]:
        state.external_tools = ctx.external_tools
        await call_llm_with_tools(ctx.provider, state, emit=ctx.emit)
        # Cap guard (shared with the legacy driver): drain pending intents
        # into synthesized is_error tool_results, flag tools_exhausted so
        # the router schedules the ONE cap-final no-tools call, and only
        # after that call salvage a placeholder if the model produced no
        # text at all.
        await enforce_tool_call_cap(state, ctx.emit)
        return _state_update(state)

    async def _dispatch_tools(state: AgentState) -> dict[str, Any]:
        state.external_tools = ctx.external_tools
        pending = list(state.pending_tool_calls)
        flagged = [c for c in pending if approval_required_for(str(c.get("name", "")))]
        if flagged:
            # interrupt() raises on first execution (pausing the turn) and
            # returns the Command(resume=...) value when the node re-runs.
            # Everything above this line is side-effect free so the
            # re-execution is safe.
            from langgraph.types import interrupt

            payload = build_approval_payload(flagged)
            decision = interrupt(payload)
            approved = bool(decision.get("approved")) if isinstance(decision, dict) else bool(decision)
            note = str(decision.get("note") or "")[:500] if isinstance(decision, dict) else ""
            await _emit_decision_ledger(ctx, state, payload, approved=approved, note=note)
            if not approved:
                await _dispatch_with_denials(ctx, state, pending, flagged, note=note)
                return _state_update(state)
        await dispatch_tools(
            ctx.session,
            state,
            emit=ctx.emit,
            turn_id_hint=ctx.turn_id,
            mcp_client=ctx.mcp_client,
            embedder=ctx.embedder,
        )
        return _state_update(state)

    async def _extract(state: AgentState) -> dict[str, Any]:
        await extract_citations(state)
        return _state_update(state)

    async def _verify(state: AgentState) -> dict[str, Any]:
        await verify_citations_parallel(ctx.session, state, emit=ctx.emit)
        return _state_update(state)

    async def _revise(state: AgentState) -> dict[str, Any]:
        state.external_tools = ctx.external_tools
        await revise_if_unverified(ctx.provider, state, emit=ctx.emit)
        return _state_update(state)

    async def _adversarial(state: AgentState) -> dict[str, Any]:
        try:
            await adversarial_review(ctx.cheap_provider, state)
        except Exception as exc:
            _log.warning("kenny v2 adversarial review failed: %s", exc)
            state.adversarial_concerns = []
            state.adversarial_concern_objs = []
        for concern in state.adversarial_concern_objs:
            await ctx.emit(
                AdversarialConcernChunk(
                    concern_text=concern.concern_text,
                    severity=concern.severity,
                )
            )
        return _state_update(state)

    async def _persist(state: AgentState) -> dict[str, Any]:
        await _persist_and_finish(ctx, state)
        return _state_update(state)

    from control_plane.agents.agent_kenny.graph import (
        NODE_ADVERSARIAL,
        NODE_DISPATCH_TOOLS,
        NODE_EXTRACT_CITATIONS,
        NODE_LLM_CALL,
        NODE_PERSIST,
        NODE_RETRIEVE,
        NODE_REVISE,
        NODE_VERIFY_CITATIONS,
    )

    return {
        NODE_RETRIEVE: _retrieve,
        NODE_LLM_CALL: _llm_call,
        NODE_DISPATCH_TOOLS: _dispatch_tools,
        NODE_EXTRACT_CITATIONS: _extract,
        NODE_VERIFY_CITATIONS: _verify,
        NODE_REVISE: _revise,
        NODE_ADVERSARIAL: _adversarial,
        NODE_PERSIST: _persist,
    }


async def _emit_decision_ledger(
    ctx: KennyRuntime,
    state: AgentState,
    payload: dict[str, str],
    *,
    approved: bool,
    note: str,
) -> None:
    verdict = "granted" if approved else "denied"
    await emit_ledger_event(
        ctx.session,
        tenant_id=state.tenant_id,
        engagement_id=state.engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=str(ctx.actor_user_id),
        source_kind=f"agent_approval_{verdict}",
        source_ref=None,
        summary=f"in-turn approval {verdict} for {payload['tool']}"[:500],
        detail={
            "tool": payload["tool"],
            "args_summary": payload["args_summary"],
            "question": payload["question"],
            "approved": approved,
            "note": note,
        },
    )


async def _dispatch_with_denials(
    ctx: KennyRuntime,
    state: AgentState,
    pending: list[dict[str, Any]],
    flagged: list[dict[str, Any]],
    *,
    note: str,
) -> None:
    """Execute the pending batch with the flagged calls replaced by denials.

    Order is preserved: the tool_result blocks in ``state.messages`` must
    line up ordinally with the assistant ``tool_use`` blocks (see
    ``llm_call._native_messages``), so denied calls get their denial
    result appended exactly where their execution result would have gone.
    """
    denied_ids = {id(c) for c in flagged}
    reason = "tool call denied by human reviewer" + (f": {note}" if note else "")
    safe_reason = reason.replace('"', "'")
    state.pending_tool_calls = []
    segment: list[dict[str, Any]] = []

    async def _flush() -> None:
        if not segment:
            return
        state.pending_tool_calls = list(segment)
        segment.clear()
        await dispatch_tools(
            ctx.session,
            state,
            emit=ctx.emit,
            turn_id_hint=ctx.turn_id,
            mcp_client=ctx.mcp_client,
            embedder=ctx.embedder,
        )

    for call in pending:
        if id(call) in denied_ids:
            await _flush()
            name = str(call.get("name", ""))
            state.messages.append(
                {
                    "role": "user",
                    "content": f'<tool_result name="{name}" error="true">{safe_reason}</tool_result>',
                }
            )
            await ctx.emit(ToolResultChunk(name=name, row_count=0, truncated=False, error="approval_denied"))
            state.tool_calls_made += 1
        else:
            segment.append(call)
    await _flush()
    state.pending_tool_calls = []


async def _persist_and_finish(ctx: KennyRuntime, state: AgentState) -> None:
    """Port of the legacy driver's security gate + persist + done emission."""
    session = ctx.session
    moment = ctx.moment

    if state.citation_report is not None and state.citation_report.cross_engagement:
        # Security gate: cross-engagement leak overrides everything. The
        # reply is replaced, the incident is ledgered, and the stripped
        # turn is still persisted for the audit trail. MUST stay
        # byte-identical to the legacy driver.
        state.security_rejected = True
        leak_count = len(state.citation_report.cross_engagement)
        leak_summary = f"kenny v2 reply REJECTED — cited {leak_count} cross-engagement id(s)"
        await emit_ledger_event(
            session,
            tenant_id=state.tenant_id,
            engagement_id=state.engagement_id,
            occurred_at=moment,
            actor_kind="agent:kenny",
            actor_id=str(state.actor_user_id),
            source_kind="agent_cross_engagement_leak",
            source_ref=None,
            summary=leak_summary[:500],
            detail={
                "actor_user_id": str(state.actor_user_id),
                "leaked_citations": [
                    {"kind": c.kind, "id": c.identifier} for c in state.citation_report.cross_engagement
                ],
                "user_message": state.user_message[:500],
            },
        )
        state.accumulated_text = _SECURITY_REJECT_REPLY
        state.final_text = _SECURITY_REJECT_REPLY
        try:
            convo, started_new = await get_or_create_conversation(
                session,
                tenant_id=state.tenant_id,
                engagement_id=state.engagement_id,
                actor_user_id=state.actor_user_id,
                conversation_id=ctx.conversation_id,
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
        await _emit_done(ctx, state)
        return

    try:
        convo, started_new = await get_or_create_conversation(
            session,
            tenant_id=state.tenant_id,
            engagement_id=state.engagement_id,
            actor_user_id=state.actor_user_id,
            conversation_id=ctx.conversation_id,
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
    await persist_concern_payload(session, state, moment=moment)
    await _emit_done(ctx, state)


async def _emit_done(ctx: KennyRuntime, state: AgentState) -> None:
    assert state.final_turn_id is not None
    assert state.final_conversation_id is not None
    await ctx.emit(
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


def _graph_config(thread_id: str) -> dict[str, Any]:
    return {
        "configurable": {"thread_id": thread_id},
        "recursion_limit": GRAPH_RECURSION_LIMIT,
    }


def _input_from_state(state: AgentState) -> dict[str, Any]:
    """Complete channel input so a reused conversation thread starts clean."""
    return _state_update(state)


async def _handle_interrupts(
    ctx: KennyRuntime,
    state: AgentState,
    result: dict[str, Any],
    *,
    thread_id: str,
) -> ApprovalRequiredChunk | None:
    """Ledger + frame for a paused run; returns the chunk when interrupted."""
    interrupts = result.get("__interrupt__") or []
    if not interrupts:
        return None
    value = interrupts[0].value
    payload = value if isinstance(value, dict) else {}
    question = str(payload.get("question", "Approve this action?"))
    tool = str(payload.get("tool", ""))
    args_summary = str(payload.get("args_summary", ""))
    await emit_ledger_event(
        ctx.session,
        tenant_id=state.tenant_id,
        engagement_id=state.engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="agent:kenny",
        actor_id=str(ctx.actor_user_id),
        source_kind="agent_approval_requested",
        source_ref=None,
        summary=f"in-turn approval requested for {tool}"[:500],
        detail={
            "tool": tool,
            "args_summary": args_summary,
            "question": question,
            "thread_id": thread_id,
        },
    )
    chunk = ApprovalRequiredChunk(
        question=question,
        tool=tool,
        args_summary=args_summary,
        thread_id=thread_id,
    )
    await ctx.emit(chunk)
    return chunk


async def run_langgraph_turn(ctx: KennyRuntime, state: AgentState) -> None:
    """Drive one turn through the checkpointed StateGraph.

    Emits the same chunk stream as the legacy driver. When the graph
    pauses on an approval interrupt, an ``approval_required`` frame is
    emitted instead of ``done`` and the function returns — the turn
    resumes later via :func:`resume_langgraph_turn`.
    """
    saver = await get_checkpointer()
    graph = build_graph(make_node_wrappers(ctx), checkpointer=saver)
    conversation_key = str(ctx.conversation_id) if ctx.conversation_id is not None else f"turn-{ctx.turn_id}"
    thread_id = build_thread_id(state.tenant_id, state.engagement_id, conversation_key)
    result: dict[str, Any] = await graph.ainvoke(_input_from_state(state), _graph_config(thread_id))
    await _handle_interrupts(ctx, state, result, thread_id=thread_id)


async def resume_langgraph_turn(
    ctx: KennyRuntime,
    *,
    thread_id: str,
    approved: bool,
    note: str,
) -> ResumeResult:
    """Resume a paused turn with the human decision (pilot-refresh D4).

    Raises :class:`ApprovalNotPendingError` when the thread has no
    interrupted run. On success the turn runs to completion (or the next
    interrupt) using the caller's fresh runtime context; chunks flow
    through ``ctx.emit`` exactly like a live stream, and the terminal
    outcome is summarized in the returned :class:`ResumeResult`.
    """
    from langgraph.types import Command

    saver = await get_checkpointer()
    graph = build_graph(make_node_wrappers(ctx), checkpointer=saver)
    config = _graph_config(thread_id)
    snapshot = await graph.aget_state(config)
    if not snapshot.values or not any(t.interrupts for t in snapshot.tasks):
        raise ApprovalNotPendingError(thread_id)

    done_holder: list[DoneChunk] = []
    inner_emit = ctx.emit

    async def _capture(chunk: Any) -> None:
        if isinstance(chunk, DoneChunk):
            done_holder.append(chunk)
        await inner_emit(chunk)

    ctx.emit = _capture
    result: dict[str, Any] = await graph.ainvoke(
        Command(resume={"approved": approved, "note": note}),
        config,
    )
    # Reconstruct the post-run state for the ledger/frame helpers. Every
    # checkpointed channel is present in the result; non-checkpointed ones
    # (external_tools) fall back to their dataclass defaults.
    state_after = AgentState(**{f.name: result[f.name] for f in dataclasses.fields(AgentState) if f.name in result})
    approval = await _handle_interrupts(ctx, state_after, result, thread_id=thread_id)
    if approval is not None:
        return ResumeResult(status="approval_required", approval=approval)
    if not done_holder:
        raise RuntimeError("resumed turn finished without a done chunk")
    return ResumeResult(status="done", done=done_holder[-1])


__all__ = [
    "AGENT_RUNTIME_ENV",
    "GRAPH_RECURSION_LIMIT",
    "RUNTIME_LANGGRAPH",
    "RUNTIME_LEGACY",
    "ApprovalNotPendingError",
    "KennyRuntime",
    "ResumeResult",
    "agent_runtime",
    "build_thread_id",
    "make_node_wrappers",
    "parse_thread_id",
    "resume_langgraph_turn",
    "run_langgraph_turn",
]
