"""Tombstone table — retention-driven destruction record (FR5, NFR33/NFR38).

``original_node_id`` intentionally has no foreign-key constraint: the
referenced row (event, identity, or learning) may already be destroyed at
the time the tombstone is written.

``tsa_timestamp`` is populated by Story 1.13 when the RFC 3161 signing
service is wired in. Until then it is ``NULL``.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Index, LargeBinary, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class Tombstone(Base):
    __tablename__ = "tombstones"

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
    original_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    retention_reason: Mapped[str] = mapped_column(nullable=False)
    authority_actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    destroyed_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    signature: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    tsa_timestamp: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)

    __table_args__ = (Index("idx_tombstones_tenant_original", "tenant_id", "original_node_id"),)
