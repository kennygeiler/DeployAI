"""Review Inbox service layer (pilot-refresh E1/E2/E3).

Creation, resolution, and dismissal of ``review_items`` rows plus their
ledger events. Every state change lands exactly one ``review_item_*``
ledger row; resolving an ``agent_escalation`` with an answer additionally
emits the canonical ``human_escalation_answer`` event — the knowledge
flywheel write path (Part 2A of the pilot-refresh design).

Callers own the transaction: these helpers ``flush`` (so ids are visible)
but never ``commit`` — same contract as ``ledger.emitter.emit_ledger_event``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.review_inbox import (
    REVIEW_ITEM_KINDS,
    REVIEW_ITEM_STATUSES,
    ReviewItem,
)
from control_plane.ledger.emitter import emit_ledger_event

_MAX_QUESTION_CHARS = 2000
_MAX_REASON_CHARS = 2000
_MAX_CONTEXT_REFS = 50


class ReviewInboxError(ValueError):
    """Domain validation failure — routes map this to HTTP 422."""


class ReviewItemNotOpenError(ReviewInboxError):
    """The item is already resolved or dismissed."""


async def create_review_item(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    kind: str,
    payload: dict[str, Any],
    created_by: str | None,
) -> ReviewItem:
    """Insert one open review item and its ``review_item_created`` ledger row."""
    if kind not in REVIEW_ITEM_KINDS:
        raise ReviewInboxError(f"invalid review item kind: {kind!r}")
    item = ReviewItem(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        kind=kind,
        status="open",
        payload=payload,
        created_by=created_by,
    )
    session.add(item)
    await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="agent" if created_by is None else "user",
        actor_id=created_by,
        source_kind="review_item_created",
        source_ref=item.id,
        summary=f"review item filed: {kind}"[:500],
        detail={"kind": kind, "payload": payload},
    )
    return item


async def file_agent_escalation(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    question: str,
    reason: str,
    context_refs: list[str] | None = None,
    created_by: str | None = None,
) -> ReviewItem:
    """E2 — the agent declines to answer and asks a human instead.

    ``context_refs`` are opaque references (event ids, node ids, turn ids)
    the agent considered relevant; they travel in the payload so the human
    answering has the same context.
    """
    question = question.strip()
    reason = reason.strip()
    if not question or len(question) > _MAX_QUESTION_CHARS:
        raise ReviewInboxError("question must be 1-2000 characters")
    if not reason or len(reason) > _MAX_REASON_CHARS:
        raise ReviewInboxError("reason must be 1-2000 characters")
    refs = [str(r) for r in (context_refs or [])][:_MAX_CONTEXT_REFS]
    return await create_review_item(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        kind="agent_escalation",
        payload={"question": question, "reason": reason, "context_refs": refs},
        created_by=created_by,
    )


async def file_citation_dispute(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    citation_id: str,
    reason: str,
    turn_id: str | None = None,
    created_by: str | None = None,
) -> ReviewItem:
    """E3 — a user flags a citation on an answer as wrong.

    The dispute is (a) a review item and (b) — via its ledger event — an
    eval-set entry for the Part 4 feedback loop (ticket G2 consumes them).
    """
    reason = reason.strip()
    if not citation_id.strip():
        raise ReviewInboxError("citation_id is required")
    if not reason or len(reason) > _MAX_REASON_CHARS:
        raise ReviewInboxError("reason must be 1-2000 characters")
    return await create_review_item(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        kind="citation_dispute",
        payload={
            "turn_id": turn_id,
            "citation_id": citation_id.strip(),
            "reason": reason,
        },
        created_by=created_by,
    )


async def resolve_review_item(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    item: ReviewItem,
    resolved_by: str | None,
    resolution_note: str | None,
    answer_text: str | None = None,
    answer_citations: list[str] | None = None,
) -> ReviewItem:
    """Resolve one open item; escalations resolved with an answer also emit
    the canonical ``human_escalation_answer`` ledger event (E2 flywheel)."""
    if item.status != "open":
        raise ReviewItemNotOpenError(f"review item is not open (status={item.status})")
    now = datetime.now(UTC)
    item.status = "resolved"
    item.resolved_by = resolved_by
    item.resolved_at = now
    item.resolution_note = resolution_note
    answer = (answer_text or "").strip()
    if item.kind == "agent_escalation" and answer:
        citations = [str(c) for c in (answer_citations or [])][:_MAX_CONTEXT_REFS]
        item.payload = {
            **(item.payload or {}),
            "answer_text": answer,
            "answer_citations": citations,
        }
        await session.flush()
        question = str((item.payload or {}).get("question", ""))
        await emit_ledger_event(
            session,
            tenant_id=tenant_id,
            engagement_id=item.engagement_id,
            occurred_at=now,
            actor_kind="user",
            actor_id=resolved_by,
            source_kind="human_escalation_answer",
            source_ref=item.id,
            summary=f"escalation answered: {question}"[:500],
            detail={
                "review_item_id": str(item.id),
                "question": question,
                "answer_text": answer,
                "citations": citations,
            },
        )
    else:
        await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=item.engagement_id,
        occurred_at=now,
        actor_kind="user",
        actor_id=resolved_by,
        source_kind="review_item_resolved",
        source_ref=item.id,
        summary=f"review item resolved: {item.kind}"[:500],
        detail={
            "kind": item.kind,
            "resolution_note": resolution_note,
            "answered": bool(item.kind == "agent_escalation" and answer),
        },
    )
    return item


async def dismiss_review_item(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    item: ReviewItem,
    resolved_by: str | None,
    resolution_note: str | None,
) -> ReviewItem:
    """Dismiss one open item (no action taken)."""
    if item.status != "open":
        raise ReviewItemNotOpenError(f"review item is not open (status={item.status})")
    now = datetime.now(UTC)
    item.status = "dismissed"
    item.resolved_by = resolved_by
    item.resolved_at = now
    item.resolution_note = resolution_note
    await session.flush()
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=item.engagement_id,
        occurred_at=now,
        actor_kind="user",
        actor_id=resolved_by,
        source_kind="review_item_dismissed",
        source_ref=item.id,
        summary=f"review item dismissed: {item.kind}"[:500],
        detail={"kind": item.kind, "resolution_note": resolution_note},
    )
    return item


async def list_review_items(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None = None,
    kind: str | None = None,
    status: str | None = None,
    limit: int = 100,
) -> list[ReviewItem]:
    if kind is not None and kind not in REVIEW_ITEM_KINDS:
        raise ReviewInboxError(f"invalid review item kind: {kind!r}")
    if status is not None and status not in REVIEW_ITEM_STATUSES:
        raise ReviewInboxError(f"invalid review item status: {status!r}")
    stmt = select(ReviewItem).where(ReviewItem.tenant_id == tenant_id)
    if engagement_id is not None:
        stmt = stmt.where(ReviewItem.engagement_id == engagement_id)
    if kind is not None:
        stmt = stmt.where(ReviewItem.kind == kind)
    if status is not None:
        stmt = stmt.where(ReviewItem.status == status)
    stmt = stmt.order_by(ReviewItem.created_at.desc()).limit(limit)
    return list((await session.execute(stmt)).scalars().all())


async def count_open_review_items(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
) -> dict[str, int]:
    """Open-item counts per kind (plus ``open`` total) for the nav badge."""
    rows = (
        await session.execute(
            select(ReviewItem.kind, func.count())
            .where(ReviewItem.tenant_id == tenant_id, ReviewItem.status == "open")
            .group_by(ReviewItem.kind)
        )
    ).all()
    by_kind = {kind: int(n) for kind, n in rows}
    return {"open": sum(by_kind.values()), **{k: by_kind.get(k, 0) for k in REVIEW_ITEM_KINDS}}


__all__ = [
    "ReviewInboxError",
    "ReviewItemNotOpenError",
    "count_open_review_items",
    "create_review_item",
    "dismiss_review_item",
    "file_agent_escalation",
    "file_citation_dispute",
    "list_review_items",
    "resolve_review_item",
]
