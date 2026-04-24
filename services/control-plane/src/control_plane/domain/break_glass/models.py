"""Break-glass session rows (Epic 2 Story 2-7; E2E operability in Epic 12)."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class BreakGlassSession(Base):
    __tablename__ = "break_glass_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    initiator_sub: Mapped[str] = mapped_column(Text(), nullable=False)
    approver_sub: Mapped[str | None] = mapped_column(Text(), nullable=True)
    requested_scope: Mapped[str] = mapped_column(Text(), nullable=False, server_default="tenant_data_read")
    status: Mapped[str] = mapped_column(Text(), nullable=False)
    requested_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    approved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    audit_transcript_ref: Mapped[str | None] = mapped_column(Text(), nullable=True)
