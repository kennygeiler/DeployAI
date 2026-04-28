"""Durable strategist operator queues (Epic 9 pilot) — action, validation, solidification."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class StrategistActionQueueItem(Base):
    __tablename__ = "strategist_action_queue_items"

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    priority: Mapped[str] = mapped_column(Text(), nullable=False)
    phase: Mapped[str] = mapped_column(Text(), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(Text(), nullable=False)
    claimed_by: Mapped[str | None] = mapped_column(Text(), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    source: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evidence_node_ids: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        server_default=text("'{}'::text[]"),
    )
    resolution_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    evidence_event_ids: Mapped[Any | None] = mapped_column(JSONB(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


class StrategistValidationQueueItem(Base):
    __tablename__ = "strategist_validation_queue_items"

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposed_fact: Mapped[str] = mapped_column(Text(), nullable=False)
    confidence: Mapped[str] = mapped_column(Text(), nullable=False)
    state: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))


class StrategistSolidificationQueueItem(Base):
    __tablename__ = "strategist_solidification_queue_items"

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proposed_fact: Mapped[str] = mapped_column(Text(), nullable=False)
    confidence: Mapped[str] = mapped_column(Text(), nullable=False)
    state: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=text("now()"))
