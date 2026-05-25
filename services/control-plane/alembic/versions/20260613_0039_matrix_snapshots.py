"""Phase F3.a — matrix_snapshots: daily materialized matrix state per engagement.

# expand-contract: expand — one new table; no changes to existing tables.

Per ``docs/design/timeline-ledger.md`` §11 F3.a. A snapshot captures the full
set of ``matrix_nodes`` + ``matrix_edges`` for one engagement at a moment in
time so the matrix-time-machine endpoint (F3.b) can serve "matrix as of <ts>"
from a nearest-prior snapshot + bounded event replay instead of replay-from-
epoch.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0039"
down_revision: str | None = "20260613_0038"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Required parent of the composite FK below — additive, no data change.
    op.create_unique_constraint(
        "uq_engagements_tenant_id_id",
        "engagements",
        ["tenant_id", "id"],
    )
    op.create_table(
        "matrix_snapshots",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
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
            nullable=False,
        ),
        sa.Column("captured_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("nodes", postgresql.JSONB(), nullable=False),
        sa.Column("edges", postgresql.JSONB(), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("node_count >= 0", name="matrix_snapshots_node_count_nonneg"),
        sa.CheckConstraint("edge_count >= 0", name="matrix_snapshots_edge_count_nonneg"),
        # Composite FK enforces (tenant_id, engagement_id) matches a real
        # engagement row — defense in depth against any path that might
        # otherwise insert mismatched tenant_id / engagement_id pairs.
        sa.ForeignKeyConstraint(
            ["tenant_id", "engagement_id"],
            ["engagements.tenant_id", "engagements.id"],
            ondelete="CASCADE",
            name="fk_matrix_snapshots_engagement_tenant",
        ),
        # DB-level idempotency: at most one snapshot per engagement per
        # captured_at. Cron normalizes captured_at to UTC midnight so a
        # second daily run for the same engagement is a guaranteed no-op.
        sa.UniqueConstraint(
            "tenant_id",
            "engagement_id",
            "captured_at",
            name="uq_matrix_snapshots_engagement_captured_at",
        ),
    )
    op.create_index(
        "ix_matrix_snapshots_engagement_captured_at",
        "matrix_snapshots",
        ["tenant_id", "engagement_id", sa.text("captured_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_matrix_snapshots_engagement_captured_at", table_name="matrix_snapshots")
    op.drop_table("matrix_snapshots")
    op.drop_constraint("uq_engagements_tenant_id_id", "engagements", type_="unique")
