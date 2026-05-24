"""ORM: meeting_webhook_events — raw landing for meeting payloads.

Phase C inc 9.2. Mirrors the D1 email-paste landing pattern: a tenant-scoped
inbox of meeting payloads received via webhook receiver or manual paste.
Downstream increments fold these into canonical memory + the matrix.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class MeetingWebhookEvent(Base):
    """A meeting payload as it arrived — pre-parse, kept for replay + audit."""

    __tablename__ = "meeting_webhook_events"
    __table_args__ = (
        Index("idx_meeting_webhook_events_tenant_id", "tenant_id"),
        Index("idx_meeting_webhook_events_engagement_id", "engagement_id"),
        Index("idx_meeting_webhook_events_received_at", "received_at"),
        Index(
            "idx_meeting_webhook_events_source_external_id",
            "tenant_id",
            "source",
            "external_event_id",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("deployai_uuid_v7()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="SET NULL"),
        nullable=True,
    )
    source: Mapped[str] = mapped_column(Text(), nullable=False)
    external_event_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB(),
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
