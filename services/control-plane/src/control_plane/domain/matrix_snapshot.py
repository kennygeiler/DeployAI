"""ORM: matrix_snapshots — daily materialized matrix state per engagement (F3.a)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class MatrixSnapshot(Base):
    """A point-in-time JSON capture of an engagement's matrix nodes + edges."""

    __tablename__ = "matrix_snapshots"

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
    captured_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    nodes: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    edges: Mapped[list[dict[str, Any]]] = mapped_column(JSONB, nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint("node_count >= 0", name="matrix_snapshots_node_count_nonneg"),
        CheckConstraint("edge_count >= 0", name="matrix_snapshots_edge_count_nonneg"),
        Index(
            "ix_matrix_snapshots_engagement_captured_at",
            "tenant_id",
            "engagement_id",
            text("captured_at DESC"),
        ),
    )


__all__ = ["MatrixSnapshot"]
