"""Ingestion integration registry (Epic 2 Story 2-6 kill-switch plumbing)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Text, func, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class Integration(Base):
    """One configured upstream integration (Calendar, Email, …) for a tenant."""

    __tablename__ = "integrations"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(Text(), nullable=False)
    display_name: Mapped[str] = mapped_column(Text(), nullable=False)
    state: Mapped[str] = mapped_column(Text(), nullable=False, server_default="active")
    config: Mapped[dict[str, Any]] = mapped_column(
        "config", JSONB(), nullable=False, server_default=text("'{}'::jsonb")
    )
    disabled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(nullable=False, server_default=func.now())
