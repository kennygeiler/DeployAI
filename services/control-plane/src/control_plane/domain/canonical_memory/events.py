"""Canonical memory event log — the immutable, append-only substrate (FR1).

The database enforces append-only via the
``canonical_memory_events_append_only`` trigger (landed in migration
``20260422_0001``). Application code MUST NOT attempt UPDATE or DELETE
— the trigger raises ``P0001 canonical_memory_events is append-only``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import BigInteger, Index, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class CanonicalMemoryEvent(Base):
    """One row = one canonical event (meeting held, email received, etc.)."""

    __tablename__ = "canonical_memory_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("deployai_uuid_v7()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    event_type: Mapped[str] = mapped_column(nullable=False)
    graph_epoch: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        server_default=text("0"),
    )
    occurred_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(nullable=True)
    ingestion_dedup_key: Mapped[str | None] = mapped_column(nullable=True)
    """``provider:source:version`` (FR18) when the row is used for at-most-once ingestion; optional."""
    evidence_span: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        Index(
            "idx_canonical_memory_events_tenant_id_created_at",
            "tenant_id",
            text("created_at DESC"),
        ),
    )
