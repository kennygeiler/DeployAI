"""Epic 11.2 — edge capture agents (per-device Ed25519 registration)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import LargeBinary, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class EdgeAgent(Base):
    """Registered macOS (later Windows) edge agent for a tenant."""

    __tablename__ = "edge_agents"
    __table_args__ = (UniqueConstraint("tenant_id", "device_id", name="uq_edge_agents_tenant_device"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("deployai_uuid_v7()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    device_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    public_key_ed25519: Mapped[bytes] = mapped_column(LargeBinary(32), nullable=False)
    registered_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
