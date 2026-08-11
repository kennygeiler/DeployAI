"""ORM for the unified Review Inbox (pilot-refresh E1).

One queue table backs three of the four inbox item kinds:

- ``agent_escalation`` (E2) — Kenny declined to answer; a human owes an
  answer that gets recorded as a canonical ledger event.
- ``citation_dispute`` (E3) — a user flagged a citation on an answer as
  wrong; resolution feeds the eval set (Part 4 feedback loop).
- ``commitment_confirmation`` — schema slot reserved now; the commitment
  extraction feature arrives in Wave 3 (ticket F3).

The fourth inbox kind, extraction proposals, deliberately keeps its
existing storage (``matrix_proposals``) — the inbox surface lists those
via the existing proposals API rather than migrating rows.

RLS: covered by migration ``20260811_0055`` with the standard
``tenant_rls_<table>`` policy shape from 0053.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base

# Kinds that are *stored* in review_items. "extraction_proposal" appears in
# the inbox UI but lives in matrix_proposals; it never lands here.
REVIEW_ITEM_KINDS: tuple[str, ...] = (
    "agent_escalation",
    "citation_dispute",
    "commitment_confirmation",
)

REVIEW_ITEM_STATUSES: tuple[str, ...] = ("open", "resolved", "dismissed")


class ReviewItem(Base):
    """One human-review queue item (async HITL, Part 2A of the pilot refresh).

    ``payload`` is shaped per ``kind``:

    - ``agent_escalation``: ``{question, reason, context_refs}`` plus, once
      resolved with an answer, ``{answer_text, answer_citations}``.
    - ``citation_dispute``: ``{turn_id, citation_id, reason}``.
    - ``commitment_confirmation``: reserved (Wave 3).
    """

    __tablename__ = "review_items"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=True,
    )
    kind: Mapped[str] = mapped_column(String(length=40), nullable=False)
    status: Mapped[str] = mapped_column(
        String(length=16),
        nullable=False,
        server_default=text("'open'"),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    created_by: Mapped[str | None] = mapped_column(String(length=200), nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(length=200), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    resolved_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "kind IN ('agent_escalation','citation_dispute','commitment_confirmation')",
            name="ck_review_items_kind",
        ),
        CheckConstraint(
            "status IN ('open','resolved','dismissed')",
            name="ck_review_items_status",
        ),
        Index("ix_review_items_tenant_status", "tenant_id", "status"),
        Index("ix_review_items_tenant_kind_status", "tenant_id", "kind", "status"),
        Index("ix_review_items_engagement", "engagement_id"),
    )


__all__ = ["REVIEW_ITEM_KINDS", "REVIEW_ITEM_STATUSES", "ReviewItem"]
