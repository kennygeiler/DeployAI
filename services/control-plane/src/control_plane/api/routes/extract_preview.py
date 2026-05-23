"""Internal API — paste-preview extraction (Sprint 2.2).

Read-only sibling of ``/internal/v1/engagements/{id}/extract`` that runs
the matrix-extraction agent against a pasted interaction *without*
writing the canonical event or any matrix proposals. The web client
uses it to show the user what the extractor would produce before they
commit, and only on Commit does the existing ``/ingest`` → ``/extract``
chain run.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from llm_provider_py.types import LLMProvider
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.llm import get_llm_provider, resolve_tenant_llm_provider
from control_plane.agents.matrix_extractor import (
    ExistingNode,
    extract_matrix_proposals,
)
from control_plane.config.internal_api import verify_internal_key
from control_plane.db import get_app_db_session
from control_plane.domain.canonical_memory.matrix import MatrixNode
from control_plane.domain.engagement import Engagement

router = APIRouter(prefix="/engagements", tags=["internal-engagements-preview"])


def _require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


_PREVIEW_SOURCES: tuple[str, ...] = ("manual_import", "meeting_note", "email", "field_note")


class ExtractPreviewCreate(BaseModel):
    source: str
    occurred_at: datetime
    content: dict[str, Any]
    source_ref: str | None = Field(default=None, max_length=500)


class ExtractPreviewDraft(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    kind: str
    payload: dict[str, Any]
    rationale: str | None


class ExtractPreviewResponse(BaseModel):
    drafts: list[ExtractPreviewDraft]


async def _require_engagement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> None:
    r = await session.execute(
        select(Engagement).where(
            Engagement.tenant_id == tenant_id,
            Engagement.id == engagement_id,
        )
    )
    if r.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")


@router.post(
    "/{engagement_id}/extract-preview",
    response_model=ExtractPreviewResponse,
    dependencies=[Depends(_require_internal)],
)
async def extract_preview(
    engagement_id: uuid.UUID,
    body: ExtractPreviewCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
) -> ExtractPreviewResponse:
    await _require_engagement(session, tenant_id, engagement_id)
    if body.source not in _PREVIEW_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid source: {body.source}",
        )
    llm = await resolve_tenant_llm_provider(session, tenant_id, llm)

    nodes_q = await session.execute(select(MatrixNode).where(MatrixNode.engagement_id == engagement_id))
    nodes = list(nodes_q.scalars().all())
    context = [ExistingNode(id=n.id, title=n.title, node_type=n.node_type) for n in nodes]

    drafts = await asyncio.to_thread(
        extract_matrix_proposals,
        event_id=uuid.uuid4(),
        event_source=f"ingest.{body.source}",
        event_occurred_at=body.occurred_at,
        event_payload={"content": body.content},
        existing_nodes=context,
        llm=llm,
    )
    return ExtractPreviewResponse(
        drafts=[ExtractPreviewDraft(kind=d.kind, payload=d.payload, rationale=d.rationale) for d in drafts]
    )
