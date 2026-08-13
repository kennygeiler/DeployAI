"""ORM for gap-ask dismissals (Wave 5, GA1 — "Kenny asks").

Asks themselves are never stored — they are recomputed deterministically by
``services.gap_detection`` on every read. Only the *user's decision to
dismiss or snooze one* persists, keyed by the ask's deterministic id so the
decision survives recomputes.

Semantics: a row with ``snooze_until IS NULL`` is a permanent dismissal; a
row with ``snooze_until`` set hides the ask until that moment, after which
it reappears. Re-dismissing/re-snoozing upserts the same row (unique on
tenant + engagement + ask).

RLS: standard forced tenant policy (0053/0058 shape) via migration
``20260813_0059``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class GapAskDismissal(Base):
    """One user decision to dismiss or snooze a deterministic gap ask."""

    __tablename__ = "gap_ask_dismissals"

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
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Deterministic ask id from gap_detection.gap_ask_id (sha256 prefix).
    ask_id: Mapped[str] = mapped_column(nullable=False)
    dismissed_by: Mapped[str | None] = mapped_column(nullable=True)
    dismissed_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    snooze_until: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "engagement_id",
            "ask_id",
            name="uq_gap_ask_dismissals_tenant_engagement_ask",
        ),
        Index("idx_gap_ask_dismissals_engagement", "tenant_id", "engagement_id"),
    )
