"""Internal API — Mr. Oracle chat (Phase G1.a).

POST a message against an engagement; the service composes context,
gates on the per-tenant LLM budget, calls the tenant-resolved provider,
persists user + oracle turns, and emits a ``oracle_chat_turn`` ledger
event wired to the upstream context_event_ids so the causal graph keeps
growing. Streaming is deferred to G1.b — this slice ships JSON only.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from llm_provider_py.types import LLMProvider
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny import ApprovalNotPendingError, KennyAgentService
from control_plane.agents.agent_kenny import (
    BudgetExhaustedError as KennyBudgetExhaustedError,
)
from control_plane.agents.agent_kenny import (
    ConversationNotFoundError as KennyConversationNotFoundError,
)
from control_plane.agents.agent_kenny.runtime import parse_thread_id
from control_plane.agents.agent_kenny.stream import format_chunk as format_kenny_chunk
from control_plane.agents.agent_kenny.types import ApprovalRequiredChunk, DoneChunk, ErrorChunk
from control_plane.agents.llm import get_llm_provider, resolve_tenant_llm_provider
from control_plane.agents.oracle_chat import (
    BudgetExhaustedError,
    ConversationNotFoundError,
    OracleChatService,
    OracleStreamDelta,
    OracleStreamDone,
)
from control_plane.api.routes.engagements_internal import _require_engagement
from control_plane.config.internal_auth import require_tenant_scoped
from control_plane.db import get_tenant_db_session
from control_plane.domain.oracle import OracleChatTurn, OracleConversation

_KENNY_V2_ENV_FLAG = "DEPLOYAI_AGENT_KENNY_V2_ENABLED"


def _kenny_v2_enabled() -> bool:
    return os.environ.get(_KENNY_V2_ENV_FLAG, "").strip().lower() in ("1", "true", "yes", "on")


router = APIRouter(prefix="/engagements", tags=["internal-engagements-oracle"])

_MAX_MESSAGE_CHARS = 4000
_ONE_DAY = timedelta(days=1)


def _actor_uuid(
    x_deployai_actor_id: str | None = Header(default=None, alias="X-DeployAI-Actor-Id"),
) -> uuid.UUID:
    if not x_deployai_actor_id or not x_deployai_actor_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-DeployAI-Actor-Id",
        )
    try:
        return uuid.UUID(x_deployai_actor_id.strip())
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-DeployAI-Actor-Id",
        ) from exc


class OracleChatRequest(BaseModel):
    conversation_id: uuid.UUID | None = None
    message: str = Field(min_length=1, max_length=_MAX_MESSAGE_CHARS)


class OracleChatResponse(BaseModel):
    turn_id: uuid.UUID
    conversation_id: uuid.UUID
    content: str
    tokens_used: int


class OracleTurnRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    tokens_used: int
    created_at: datetime


class OracleHistoryResponse(BaseModel):
    conversation_id: uuid.UUID | None
    turns: list[OracleTurnRead]


@router.post(
    "/{engagement_id}/oracle/chat",
    response_model=OracleChatResponse,
    dependencies=[Depends(require_tenant_scoped)],
)
async def post_oracle_chat(
    engagement_id: uuid.UUID,
    body: OracleChatRequest,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    actor_id: Annotated[uuid.UUID, Depends(_actor_uuid)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> OracleChatResponse:
    engagement = await _require_engagement(session, tenant_id, engagement_id)
    resolved = await resolve_tenant_llm_provider(session, tenant_id, llm)
    service = OracleChatService(resolved)
    try:
        reply = await asyncio.shield(
            service.reply(
                session,
                tenant_id=tenant_id,
                engagement=engagement,
                actor_user_id=actor_id,
                conversation_id=body.conversation_id,
                message=body.message,
                now=datetime.now(UTC),
            )
        )
    except BudgetExhaustedError as exc:
        await session.rollback()
        tomorrow = datetime.now(UTC).date() + _ONE_DAY
        retry_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=UTC).isoformat()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "daily LLM budget exhausted", "retry_after_iso": retry_at},
        ) from exc
    except ConversationNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found") from exc
    await session.commit()
    return OracleChatResponse(
        turn_id=reply.turn_id,
        conversation_id=reply.conversation_id,
        content=reply.content,
        tokens_used=reply.tokens_used,
    )


_log = logging.getLogger(__name__)


@router.post(
    "/{engagement_id}/oracle/chat/stream",
    dependencies=[Depends(require_tenant_scoped)],
)
async def post_oracle_chat_stream(
    engagement_id: uuid.UUID,
    body: OracleChatRequest,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    actor_id: Annotated[uuid.UUID, Depends(_actor_uuid)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> StreamingResponse:
    engagement = await _require_engagement(session, tenant_id, engagement_id)
    resolved = await resolve_tenant_llm_provider(session, tenant_id, llm)
    service = OracleChatService(resolved)

    # reply_stream() runs pre-flight (validate / budget / user-turn / prompt)
    # eagerly so 404 / 429 surface here as HTTPException before any SSE frame.
    try:
        chunks = await service.reply_stream(
            session,
            tenant_id=tenant_id,
            engagement=engagement,
            actor_user_id=actor_id,
            conversation_id=body.conversation_id,
            message=body.message,
            now=datetime.now(UTC),
        )
    except BudgetExhaustedError as exc:
        await session.rollback()
        tomorrow = datetime.now(UTC).date() + _ONE_DAY
        retry_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=UTC).isoformat()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "daily LLM budget exhausted", "retry_after_iso": retry_at},
        ) from exc
    except ConversationNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found") from exc

    async def _frames() -> AsyncIterator[bytes]:
        try:
            async for chunk in chunks:
                if isinstance(chunk, OracleStreamDelta):
                    payload: dict[str, object] = {"delta": chunk.delta, "done": False}
                    yield f"data: {json.dumps(payload)}\n\n".encode()
                else:
                    assert isinstance(chunk, OracleStreamDone)
                    await session.commit()
                    done_payload: dict[str, object] = {
                        "done": True,
                        "turn_id": str(chunk.turn_id),
                        "conversation_id": str(chunk.conversation_id),
                        "tokens_used": chunk.tokens_used,
                    }
                    yield f"data: {json.dumps(done_payload)}\n\n".encode()
        except Exception as exc:
            await session.rollback()
            _log.exception("oracle stream error")
            err_payload = {"done": True, "error": str(exc)[:200]}
            yield f"data: {json.dumps(err_payload)}\n\n".encode()

    return StreamingResponse(
        _frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store"},
    )


@router.post(
    "/{engagement_id}/oracle/chat/stream-v2",
    dependencies=[Depends(require_tenant_scoped)],
)
async def post_oracle_chat_stream_v2(
    request: Request,
    engagement_id: uuid.UUID,
    body: OracleChatRequest,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    actor_id: Annotated[uuid.UUID, Depends(_actor_uuid)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> StreamingResponse:
    if not _kenny_v2_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    await _require_engagement(session, tenant_id, engagement_id)
    resolved = await resolve_tenant_llm_provider(session, tenant_id, llm)
    # Wave 3G: pull the outbound-MCP singletons from app.state (installed
    # by main.py's _lifespan via mcp_factory.install_on_app_state). Falls
    # back to None when the lifespan hasn't installed them (test cases
    # that build the FastAPI app without the lifespan hook still work,
    # they just don't get external MCP).
    mcp_client = getattr(request.app.state, "mcp_outbound_client", None)
    mcp_kill_switch = getattr(request.app.state, "mcp_kill_switch", None)
    mcp_rate_limiter = getattr(request.app.state, "mcp_rate_limiter", None)
    # Phase 5.5 Wave C: the Voyage embedder is installed on app.state by
    # mcp_factory.install_on_app_state. Resolves to None until Wave B
    # lands the concrete VoyageClient — vector_search calls then surface
    # as is_error tool_results without crashing the turn.
    embedder = getattr(request.app.state, "embedder", None)
    service = KennyAgentService(
        resolved,
        mcp_client=mcp_client,
        mcp_kill_switch=mcp_kill_switch,
        mcp_rate_limiter=mcp_rate_limiter,
        embedder=embedder,
    )

    try:
        chunks = await service.reply_stream(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            actor_user_id=actor_id,
            conversation_id=body.conversation_id,
            message=body.message,
            now=datetime.now(UTC),
        )
    except KennyBudgetExhaustedError as exc:
        await session.rollback()
        tomorrow = datetime.now(UTC).date() + _ONE_DAY
        retry_at = datetime.combine(tomorrow, datetime.min.time(), tzinfo=UTC).isoformat()
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"error": "daily LLM budget exhausted", "retry_after_iso": retry_at},
        ) from exc
    except KennyConversationNotFoundError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="conversation not found") from exc

    async def _frames() -> AsyncIterator[bytes]:
        committed = False
        try:
            async for chunk in chunks:
                if isinstance(chunk, DoneChunk):
                    if not committed:
                        await session.commit()
                        committed = True
                    yield format_kenny_chunk(chunk)
                elif isinstance(chunk, ApprovalRequiredChunk):
                    # D4: the turn is paused on a human approval. Commit so
                    # the agent_approval_requested ledger row survives; the
                    # LangGraph checkpoint persists via its own pool. The
                    # stream ends after this frame (no `done`); the client
                    # resumes via POST /oracle/approvals/{thread_id}.
                    if not committed:
                        await session.commit()
                        committed = True
                    yield format_kenny_chunk(chunk)
                elif isinstance(chunk, ErrorChunk):
                    if not committed:
                        await session.rollback()
                    yield format_kenny_chunk(chunk)
                else:
                    yield format_kenny_chunk(chunk)
        except Exception as exc:
            if not committed:
                await session.rollback()
            _log.exception("kenny v2 stream error")
            yield format_kenny_chunk(ErrorChunk(error=str(exc)[:200]))

    return StreamingResponse(
        _frames(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store"},
    )


class OracleApprovalDecisionRequest(BaseModel):
    approved: bool
    note: str | None = Field(default=None, max_length=500)


class OracleApprovalPayload(BaseModel):
    question: str
    tool: str
    args_summary: str
    thread_id: str


class OracleApprovalResumeResponse(BaseModel):
    """Outcome of resuming an approval-paused turn.

    ``status == "done"``: the turn completed; the reply fields mirror the
    non-streaming chat response (this endpoint is deliberately
    non-streaming — it matches the web client's existing JSON fallback
    tier, so no new stream re-attachment machinery is needed).
    ``status == "approval_required"``: the resumed run paused on another
    approval; ``approval`` carries the new prompt for the same thread.
    """

    status: str
    turn_id: uuid.UUID | None = None
    conversation_id: uuid.UUID | None = None
    content: str | None = None
    tokens_used: int | None = None
    approval: OracleApprovalPayload | None = None


@router.post(
    "/{engagement_id}/oracle/approvals/{thread_id}",
    response_model=OracleApprovalResumeResponse,
    dependencies=[Depends(require_tenant_scoped)],
)
async def post_oracle_approval_decision(
    request: Request,
    engagement_id: uuid.UUID,
    thread_id: str,
    body: OracleApprovalDecisionRequest,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    actor_id: Annotated[uuid.UUID, Depends(_actor_uuid)],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> OracleApprovalResumeResponse:
    """Resume a turn paused on an in-turn approval (pilot-refresh D4)."""
    if not _kenny_v2_enabled():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")

    parsed = parse_thread_id(thread_id)
    if parsed is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="malformed thread id")
    thread_tenant, thread_engagement, _key = parsed
    # The thread key carries its own tenant/engagement scope — it must
    # match the authenticated route scope or the thread does not exist
    # for this caller.
    if thread_tenant != tenant_id or thread_engagement != engagement_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval not found")

    await _require_engagement(session, tenant_id, engagement_id)
    resolved = await resolve_tenant_llm_provider(session, tenant_id, llm)
    service = KennyAgentService(
        resolved,
        mcp_client=getattr(request.app.state, "mcp_outbound_client", None),
        mcp_kill_switch=getattr(request.app.state, "mcp_kill_switch", None),
        mcp_rate_limiter=getattr(request.app.state, "mcp_rate_limiter", None),
        embedder=getattr(request.app.state, "embedder", None),
    )
    try:
        outcome = await service.resume_approval(
            session,
            thread_id=thread_id,
            approved=body.approved,
            note=(body.note or "").strip(),
            actor_user_id=actor_id,
            now=datetime.now(UTC),
        )
    except ApprovalNotPendingError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="approval not found") from exc
    except TimeoutError as exc:
        await session.rollback()
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="turn_timeout") from exc
    except Exception:
        await session.rollback()
        _log.exception("kenny approval resume failed")
        raise

    await session.commit()
    if outcome.status == "approval_required":
        approval = outcome.approval
        assert approval is not None
        return OracleApprovalResumeResponse(
            status="approval_required",
            approval=OracleApprovalPayload(
                question=approval.question,
                tool=approval.tool,
                args_summary=approval.args_summary,
                thread_id=approval.thread_id,
            ),
        )
    done = outcome.done
    assert done is not None
    return OracleApprovalResumeResponse(
        status="done",
        turn_id=done.turn_id,
        conversation_id=done.conversation_id,
        content=done.final_text,
        tokens_used=done.tokens,
    )


@router.get(
    "/{engagement_id}/oracle/history",
    response_model=OracleHistoryResponse,
    dependencies=[Depends(require_tenant_scoped)],
)
async def get_oracle_history(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    actor_id: Annotated[uuid.UUID, Depends(_actor_uuid)],
) -> OracleHistoryResponse:
    await _require_engagement(session, tenant_id, engagement_id)
    convo_q = await session.execute(
        select(OracleConversation).where(
            OracleConversation.tenant_id == tenant_id,
            OracleConversation.engagement_id == engagement_id,
            OracleConversation.actor_user_id == actor_id,
        )
    )
    convo = convo_q.scalar_one_or_none()
    if convo is None:
        return OracleHistoryResponse(conversation_id=None, turns=[])
    turns_q = await session.execute(
        select(OracleChatTurn)
        .where(
            OracleChatTurn.conversation_id == convo.id,
            OracleChatTurn.tenant_id == tenant_id,
        )
        .order_by(OracleChatTurn.created_at.asc())
    )
    turns = list(turns_q.scalars().all())
    return OracleHistoryResponse(
        conversation_id=convo.id,
        turns=[OracleTurnRead.model_validate(t) for t in turns],
    )
