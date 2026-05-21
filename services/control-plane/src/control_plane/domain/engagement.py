"""ORM: engagements — one customer deployment within a tenant (team).

Phase 1 of the team-tracking pivot. A tenant is the team / company; an
engagement is one customer deployment that team runs, with its own phase.
``engagement_members`` links team users to an engagement with a role — the
seam Phase 2 (roles) and Phase 4 (collaboration) build on. See
``docs/product/deployai-source-of-truth-spec.md`` section 16.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class Engagement(Base):
    """One customer deployment, owned by a tenant (the team)."""

    __tablename__ = "engagements"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    customer_account: Mapped[str | None] = mapped_column(Text(), nullable=True)
    current_phase: Mapped[str] = mapped_column(Text(), nullable=False, server_default="P1_pre_engagement")
    status: Mapped[str] = mapped_column(Text(), nullable=False, server_default="active")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class EngagementMember(Base):
    """Links a tenant user to an engagement with a role (fde / deployment_strategist / biz_dev)."""

    __tablename__ = "engagement_members"
    __table_args__ = (UniqueConstraint("engagement_id", "user_id", name="uq_engagement_members_engagement_id_user_id"),)

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())


class EngagementLogEntry(Base):
    """A manually-logged entry on an engagement — meeting / decision / risk /
    next-action (Phase 3, manual capture). See source-of-truth spec §16."""

    __tablename__ = "engagement_log_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("engagements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entry_kind: Mapped[str] = mapped_column(Text(), nullable=False)
    body: Mapped[str] = mapped_column(Text(), nullable=False)
    author: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=func.now())
