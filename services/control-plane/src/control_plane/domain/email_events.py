"""ORM: email_ingest_events — raw landing for email payloads.

Phase C inc 9.1. Mirrors the 9.2 meeting webhook landing pattern: a
tenant-scoped inbox of email payloads received via paste (IMAP/MBOX text)
or, once OAuth lands, via the Gmail / M365 connector. Downstream
increments fold these into canonical memory + the matrix.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class EmailIngestEvent(Base):
    """An email payload as it arrived — pre-parse, kept for replay + audit."""

    __tablename__ = "email_ingest_events"
    __table_args__ = (
        Index("idx_email_ingest_events_tenant_id", "tenant_id"),
        Index("idx_email_ingest_events_engagement_id", "engagement_id"),
        Index("idx_email_ingest_events_received_at", "received_at"),
        Index(
            "idx_email_ingest_events_source_external_id",
            "tenant_id",
            "source",
            "external_message_id",
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
    external_message_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # Raw email text (RFC 5322 message or mbox slice). Stored as TEXT — emails
    # are line-oriented strings; JSONB would force a useless extra escape.
    raw_payload: Mapped[str] = mapped_column(Text(), nullable=False)
    parsed_subject: Mapped[str | None] = mapped_column(Text(), nullable=True)
    parsed_from: Mapped[str | None] = mapped_column(Text(), nullable=True)
    parsed_to: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        server_default=text("ARRAY[]::text[]"),
    )
    parsed_date: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    processed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text(), nullable=True)
