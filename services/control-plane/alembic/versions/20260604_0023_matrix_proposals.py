"""Phase 6 (increment 6.2a) — matrix_proposals.

# expand-contract: expand — one new table; no changes to existing tables.

Matrix proposals are the human-review buffer between the Phase 6 extraction
agent (Cartographer, lands in 6.2b) and the committed matrix. A proposal
references the canonical event it was derived from (``source_event_id``);
its payload carries the proposed node/edge shape; accepting commits it to
``matrix_nodes`` / ``matrix_edges`` with ``evidence_event_ids = [source_event_id]``
— the retrieval-bound principle made visible. See
``docs/product/deployment-matrix-model.md`` and the §16 Phase 6 plan.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260604_0023"
down_revision: str | None = "20260603_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matrix_proposals",
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
        sa.Column(
            "source_event_id",
            postgresql.UUID(as_uuid=True),
            # RESTRICT: canonical_memory_events is append-only; CASCADE / SET NULL
            # would mutate event rows and trip the append-only trigger.
            sa.ForeignKey("canonical_memory_events.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("proposal_kind", sa.Text(), nullable=False),  # "node" | "edge"
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.Column(
            "result_node_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matrix_nodes.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "result_edge_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("matrix_edges.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("idx_matrix_proposals_tenant_id", "matrix_proposals", ["tenant_id"])
    op.create_index(
        "idx_matrix_proposals_engagement_status",
        "matrix_proposals",
        ["engagement_id", "status"],
    )
    op.create_index("idx_matrix_proposals_source_event_id", "matrix_proposals", ["source_event_id"])


def downgrade() -> None:
    op.drop_table("matrix_proposals")
