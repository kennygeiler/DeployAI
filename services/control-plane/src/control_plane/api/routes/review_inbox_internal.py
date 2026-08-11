"""Internal API: unified Review Inbox (pilot-refresh E1/E2/E3).

Lists and mutates ``review_items`` — agent escalations, citation disputes,
and (Wave 3) commitment confirmations. Extraction proposals stay on their
existing storage and API (``engagements_internal``); the web inbox merges
the two sources client-side.

The escalation-filing route exists so the agent runtime can decline +
escalate over HTTP once the D-lane wires the caller; until then the BFF
and tests are the only clients.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_auth import require_tenant_scoped
from control_plane.db import get_tenant_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.engagement import Engagement
from control_plane.domain.review_inbox import ReviewItem
from control_plane.services.review_inbox import (
    ReviewInboxError,
    ReviewItemNotOpenError,
    count_open_review_items,
    dismiss_review_item,
    file_agent_escalation,
    file_citation_dispute,
    list_review_items,
    resolve_review_item,
)

router = APIRouter(prefix="/review-items", tags=["internal-review-inbox"])

_DEFAULT_LIMIT = 100
_MAX_LIMIT = 500


class ReviewItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    kind: str
    status: str
    payload: dict[str, Any]
    created_by: str | None
    resolved_by: str | None
    resolution_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class ReviewItemCounts(BaseModel):
    open: int
    agent_escalation: int
    citation_dispute: int
    commitment_confirmation: int


class EscalationCreate(BaseModel):
    engagement_id: uuid.UUID
    question: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=2000)
    context_refs: list[str] = Field(default_factory=list, max_length=50)
    created_by: str | None = Field(default=None, max_length=200)


class CitationDisputeCreate(BaseModel):
    engagement_id: uuid.UUID | None = None
    turn_id: str | None = Field(default=None, max_length=200)
    citation_id: str = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=1, max_length=2000)
    created_by: str | None = Field(default=None, max_length=200)


class ReviewItemResolveBody(BaseModel):
    resolved_by: str | None = Field(default=None, max_length=200)
    resolution_note: str | None = Field(default=None, max_length=2000)
    # E2 — answering an escalation records the canonical
    # ``human_escalation_answer`` ledger event with these fields.
    answer_text: str | None = Field(default=None, max_length=8000)
    answer_citations: list[str] = Field(default_factory=list, max_length=50)


class ReviewItemDismissBody(BaseModel):
    resolved_by: str | None = Field(default=None, max_length=200)
    resolution_note: str | None = Field(default=None, max_length=2000)


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    if await session.get(AppTenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")


async def _require_engagement(session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> None:
    row = (
        await session.execute(
            select(Engagement.id).where(
                Engagement.tenant_id == tenant_id,
                Engagement.id == engagement_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")


async def _require_item(session: AsyncSession, tenant_id: uuid.UUID, item_id: uuid.UUID) -> ReviewItem:
    row = (
        await session.execute(
            select(ReviewItem).where(
                ReviewItem.tenant_id == tenant_id,
                ReviewItem.id == item_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="review item not found")
    return row


@router.get(
    "",
    response_model=list[ReviewItemRead],
    dependencies=[Depends(require_tenant_scoped)],
)
async def list_items(
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    engagement_id: Annotated[uuid.UUID | None, Query()] = None,
    kind: Annotated[str | None, Query(max_length=40)] = None,
    status_: Annotated[str | None, Query(alias="status", max_length=16)] = None,
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> list[ReviewItem]:
    await _require_tenant(session, tenant_id)
    try:
        return await list_review_items(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            kind=kind,
            status=status_,
            limit=limit,
        )
    except ReviewInboxError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc


@router.get(
    "/counts",
    response_model=ReviewItemCounts,
    dependencies=[Depends(require_tenant_scoped)],
)
async def get_counts(
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ReviewItemCounts:
    await _require_tenant(session, tenant_id)
    counts = await count_open_review_items(session, tenant_id=tenant_id)
    return ReviewItemCounts(**counts)


@router.post(
    "/escalations",
    response_model=ReviewItemRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_tenant_scoped)],
)
async def create_escalation(
    body: EscalationCreate,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ReviewItem:
    """E2 — the agent runtime files an escalation instead of answering."""
    await _require_tenant(session, tenant_id)
    await _require_engagement(session, tenant_id, body.engagement_id)
    try:
        item = await file_agent_escalation(
            session,
            tenant_id=tenant_id,
            engagement_id=body.engagement_id,
            question=body.question,
            reason=body.reason,
            context_refs=body.context_refs,
            created_by=body.created_by,
        )
    except ReviewInboxError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return item


@router.post(
    "/citation-disputes",
    response_model=ReviewItemRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_tenant_scoped)],
)
async def create_citation_dispute(
    body: CitationDisputeCreate,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ReviewItem:
    """E3 — a user flags a wrong citation; becomes a review item + eval-set entry."""
    await _require_tenant(session, tenant_id)
    if body.engagement_id is not None:
        await _require_engagement(session, tenant_id, body.engagement_id)
    try:
        item = await file_citation_dispute(
            session,
            tenant_id=tenant_id,
            engagement_id=body.engagement_id,
            citation_id=body.citation_id,
            reason=body.reason,
            turn_id=body.turn_id,
            created_by=body.created_by,
        )
    except ReviewInboxError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return item


@router.post(
    "/{item_id}/resolve",
    response_model=ReviewItemRead,
    dependencies=[Depends(require_tenant_scoped)],
)
async def resolve_item(
    item_id: uuid.UUID,
    body: ReviewItemResolveBody,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ReviewItem:
    await _require_tenant(session, tenant_id)
    item = await _require_item(session, tenant_id, item_id)
    try:
        await resolve_review_item(
            session,
            tenant_id=tenant_id,
            item=item,
            resolved_by=body.resolved_by,
            resolution_note=body.resolution_note,
            answer_text=body.answer_text,
            answer_citations=body.answer_citations,
        )
    except ReviewItemNotOpenError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return item


@router.post(
    "/{item_id}/dismiss",
    response_model=ReviewItemRead,
    dependencies=[Depends(require_tenant_scoped)],
)
async def dismiss_item(
    item_id: uuid.UUID,
    body: ReviewItemDismissBody,
    session: Annotated[AsyncSession, Depends(get_tenant_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ReviewItem:
    await _require_tenant(session, tenant_id)
    item = await _require_item(session, tenant_id, item_id)
    try:
        await dismiss_review_item(
            session,
            tenant_id=tenant_id,
            item=item,
            resolved_by=body.resolved_by,
            resolution_note=body.resolution_note,
        )
    except ReviewItemNotOpenError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)) from exc
    await session.commit()
    await session.refresh(item)
    return item
