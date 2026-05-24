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

from sqlalchemy import ForeignKey, Index, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base

# Catalogs of valid node_type / edge_type values. Treated as data, not schema:
# adopting teams add custom types here (or via a future per-tenant catalog
# table). Single source of truth — imported by the CRUD API, the proposal
# accept path, and the Phase 6 extraction agent so the prompt drifts together
# with the schema. See `deployment-matrix-model.md` §6 (extension seam).
MATRIX_NODE_TYPES: tuple[str, ...] = (
    "stakeholder",
    "organization",
    "system",
    "decision",
    "risk",
    "commitment",
    "opportunity",
)
MATRIX_EDGE_TYPES: tuple[str, ...] = (
    "belongs_to",
    "owns",
    "sponsors",
    "blocks",
    "affects",
    "threatens",
    "owed_by",
    "owed_to",
    "depends_on",
    "enables",
)


class TenantNodeType(Base):
    """A tenant-registered custom matrix node type — extends MATRIX_NODE_TYPES."""

    __tablename__ = "tenant_node_types"

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
    name: Mapped[str] = mapped_column(nullable=False)
    label: Mapped[str] = mapped_column(nullable=False)
    color: Mapped[str | None] = mapped_column(nullable=True)
    description: Mapped[str | None] = mapped_column(nullable=True)
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
        UniqueConstraint("tenant_id", "name", name="uq_tenant_node_types_tenant_name"),
        Index("idx_tenant_node_types_tenant_id", "tenant_id"),
    )


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


class MatrixProposal(Base):
    """A proposed matrix node or edge derived from a canonical event.

    Lives between the Phase 6 extraction agent (Cartographer, 6.2b) and the
    committed matrix: accept commits it as a node/edge with
    ``evidence_event_ids = [source_event_id]``; reject closes it out.
    """

    __tablename__ = "matrix_proposals"

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
    source_event_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("canonical_memory_events.id", ondelete="RESTRICT"),
        nullable=False,
    )
    proposal_kind: Mapped[str] = mapped_column(nullable=False)  # "node" | "edge"
    payload: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )
    rationale: Mapped[str | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(nullable=False, server_default=text("'pending'"))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(nullable=True)
    result_node_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matrix_nodes.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_edge_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("matrix_edges.id", ondelete="SET NULL"),
        nullable=True,
    )

    __table_args__ = (
        Index("idx_matrix_proposals_tenant_id", "tenant_id"),
        Index("idx_matrix_proposals_engagement_status", "engagement_id", "status"),
        Index("idx_matrix_proposals_source_event_id", "source_event_id"),
    )


# --- Phase 7 (increment 7.2): matrix insights -------------------------------
#
# Insights are observations produced by Oracle (per-engagement) and Master
# Strategist (cross-engagement). Unlike proposals, accepting an insight does
# not mutate the matrix — they are observations, not graph edits. Status moves
# open → dismissed | resolved (user action) or → resolved (auto, when the
# predicate that produced the insight no longer fires).

INSIGHT_AGENTS: tuple[str, ...] = ("oracle", "master_strategist")
INSIGHT_SEVERITIES: tuple[str, ...] = ("low", "medium", "high")
INSIGHT_STATUSES: tuple[str, ...] = ("open", "dismissed", "resolved")


class MatrixInsight(Base):
    """An observation derived from the matrix by a synthesis agent.

    ``engagement_id`` is nullable — null = tenant-scoped insight (Master
    Strategist). ``dedup_key`` is UNIQUE; refresh upserts in place.
    """

    __tablename__ = "matrix_insights"

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
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=True,
    )
    agent: Mapped[str] = mapped_column(nullable=False)
    insight_type: Mapped[str] = mapped_column(nullable=False)
    severity: Mapped[str] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(nullable=False)
    body: Mapped[str] = mapped_column(nullable=False)
    citation_node_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    citation_edge_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    citation_event_ids: Mapped[list[uuid.UUID]] = mapped_column(
        ARRAY(UUID(as_uuid=True)),
        nullable=False,
        server_default=text("'{}'::uuid[]"),
    )
    dedup_key: Mapped[str] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(nullable=False, server_default=text("'open'"))
    input_hash: Mapped[str | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    decided_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(nullable=True)

    __table_args__ = (
        Index(
            "idx_matrix_insights_engagement_status",
            "tenant_id",
            "engagement_id",
            "status",
        ),
        Index(
            "idx_matrix_insights_tenant_agent_status",
            "tenant_id",
            "agent",
            "status",
        ),
        Index("uq_matrix_insights_dedup_key", "dedup_key", unique=True),
    )
