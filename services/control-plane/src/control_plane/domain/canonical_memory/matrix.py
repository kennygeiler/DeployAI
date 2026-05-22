"""Deployment matrix — the typed property graph (Phase 5).

The matrix is the structured *map* of a deployment: ``MatrixNode`` entities
(stakeholder / organization / system / decision / risk / commitment /
opportunity) joined by typed ``MatrixEdge`` relationships. Both are
engagement-scoped and cite the canonical events that evidence them via
``evidence_event_ids`` — the retrieval-bound principle, mirroring
``solidified_learnings``.

Node/edge types are ``TEXT`` and type-specific data is JSONB ``attributes``,
so a custom entity or relationship type needs no migration — the extension
seam. Unlike the append-only event log, matrix rows are mutable. See
``docs/product/deployment-matrix-model.md``.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import ForeignKey, Index, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class MatrixNode(Base):
    """One entity in a deployment's matrix — a typed, engagement-scoped node."""

    __tablename__ = "matrix_nodes"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("deployai_uuid_v7()"),
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
    node_type: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    identity_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("identity_nodes.id", ondelete="RESTRICT"),
        nullable=True,
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    status: Mapped[str | None] = mapped_column(nullable=True)
    evidence_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        Index("idx_matrix_nodes_tenant_id", "tenant_id"),
        Index("idx_matrix_nodes_engagement_id", "engagement_id"),
        Index("idx_matrix_nodes_engagement_type", "engagement_id", "node_type"),
    )


class MatrixEdge(Base):
    """A typed, directional relationship between two matrix nodes."""

    __tablename__ = "matrix_edges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("deployai_uuid_v7()"),
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
    edge_type: Mapped[str] = mapped_column(nullable=False)
    from_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matrix_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    to_node_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matrix_nodes.id", ondelete="CASCADE"),
        nullable=False,
    )
    attributes: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    evidence_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )

    __table_args__ = (
        Index("idx_matrix_edges_tenant_id", "tenant_id"),
        Index("idx_matrix_edges_engagement_id", "engagement_id"),
        Index("idx_matrix_edges_from_node_id", "from_node_id"),
        Index("idx_matrix_edges_to_node_id", "to_node_id"),
    )
