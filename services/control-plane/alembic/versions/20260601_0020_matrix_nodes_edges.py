"""Phase 5 (increment 5.2a) — deployment-matrix property graph.

# expand-contract: expand — two new tables; no changes to existing tables.

The deployment matrix is a typed property graph: ``matrix_nodes`` (the
entities — stakeholder / organization / system / decision / risk /
commitment / opportunity) joined by typed ``matrix_edges``. Both are
engagement-scoped and carry ``evidence_event_ids`` — the canonical events
that evidence the node/edge (the retrieval-bound principle, mirroring
``solidified_learnings``). Per the decision record, the matrix uses
``deployai_uuid_v7()`` ids and app-layer tenant/engagement filtering (no
RLS) — it is an internal-API operational table like ``engagements`` and the
strategist queues. See ``docs/product/deployment-matrix-model.md`` and
``deployai-source-of-truth-spec.md`` section 16 (Phase 5).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260601_0020"
down_revision: str | None = "20260531_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matrix_nodes",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("deployai_uuid_v7()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("node_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column(
            "identity_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("identity_nodes.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("status", sa.Text(), nullable=True),
        sa.Column(
            "evidence_event_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_matrix_nodes_tenant_id", "matrix_nodes", ["tenant_id"])
    op.create_index("idx_matrix_nodes_engagement_id", "matrix_nodes", ["engagement_id"])
    op.create_index("idx_matrix_nodes_engagement_type", "matrix_nodes", ["engagement_id", "node_type"])

    op.create_table(
        "matrix_edges",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("deployai_uuid_v7()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("edge_type", sa.Text(), nullable=False),
        sa.Column(
            "from_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matrix_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matrix_nodes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("attributes", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "evidence_event_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_matrix_edges_tenant_id", "matrix_edges", ["tenant_id"])
    op.create_index("idx_matrix_edges_engagement_id", "matrix_edges", ["engagement_id"])
    op.create_index("idx_matrix_edges_from_node_id", "matrix_edges", ["from_node_id"])
    op.create_index("idx_matrix_edges_to_node_id", "matrix_edges", ["to_node_id"])


def downgrade() -> None:
    op.drop_table("matrix_edges")
    op.drop_table("matrix_nodes")
