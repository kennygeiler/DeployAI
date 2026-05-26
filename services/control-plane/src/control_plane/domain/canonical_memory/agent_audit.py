"""ORM: agent_audit_traces (v2 Phase 2/3).

One row per Agent Kenny v2 chat turn. Carries the per-turn citation
totals, tool-call count, revision attempts, adversarial-concerns count
and the final reply text so the Phase 6 hallucination dashboard can
compute trend metrics without re-aggregating across ledger rows.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    TIMESTAMP,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class AgentAuditTrace(Base):
    """One audit row per Agent Kenny v2 turn."""

    __tablename__ = "agent_audit_traces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    engagement_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=False,
    )
    turn_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    total_citations: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    verified_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    unverified_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    cross_engagement_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    external_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    revision_attempts: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    adversarial_concerns_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    tool_calls_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    total_tokens: Mapped[int] = mapped_column(Integer(), nullable=False, server_default=text("0"))
    duration_ms: Mapped[float] = mapped_column(Float(), nullable=False, server_default=text("0"))
    final_text: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        Index(
            "agent_audit_traces_by_engagement",
            "tenant_id",
            "engagement_id",
            "created_at",
        ),
    )


__all__ = ["AgentAuditTrace"]
