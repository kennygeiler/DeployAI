"""ORM: per-engagement inbound email intake addresses (Wave 5 IN1).

One ACTIVE row per engagement (partial unique index in migration 0059);
regenerate revokes the old row (``revoked_at``) and inserts a new one, so
deliveries to a stale address are recognizably "revoked" rather than
indistinguishable from garbage.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class EngagementIntakeAddress(Base):
    """Maps an email local part (``<slug>-<token>``) to one engagement."""

    __tablename__ = "engagement_intake_addresses"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False
    )
    local_part: Mapped[str] = mapped_column(Text(), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
