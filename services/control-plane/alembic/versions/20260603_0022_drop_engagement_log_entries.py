"""Phase 5 (increment 5.5) — drop engagement_log_entries.

# expand-contract: contract — the Phase 3 journal is superseded by the
deployment matrix (`matrix_nodes` / `matrix_edges`). The detail-page Log
section, the cross-role activity view, the role lens, and the
``EngagementCaptureForm`` are removed at the same time on the web side.
See ``docs/product/deployai-source-of-truth-spec.md`` section 16 (Phase 5)
and ``docs/product/deployment-matrix-model.md`` section 7.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260603_0022"
down_revision: str | None = "20260602_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("idx_engagement_log_entries_engagement_id", table_name="engagement_log_entries")
    op.drop_index("idx_engagement_log_entries_tenant_id", table_name="engagement_log_entries")
    op.drop_table("engagement_log_entries")


def downgrade() -> None:
    # Recreate the journal as 0018 + 0019 left it.
    op.create_table(
        "engagement_log_entries",
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
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("entry_kind", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("author", sa.Text(), nullable=True),
        sa.Column("author_role", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("idx_engagement_log_entries_tenant_id", "engagement_log_entries", ["tenant_id"])
    op.create_index("idx_engagement_log_entries_engagement_id", "engagement_log_entries", ["engagement_id"])
