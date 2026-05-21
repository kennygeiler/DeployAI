"""Phase 3 — engagement_log_entries (manual capture).

# expand-contract: expand — one new table; no changes to existing tables.

A per-engagement log of manually-entered meeting / decision / risk /
next-action notes. Distinct from ``canonical_memory_events`` (the agent
extraction log): this is operator-entered, engagement-scoped, and has no
citation-envelope shape. See ``docs/product/deployai-source-of-truth-spec.md``
section 16 (Phase 3).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260530_0018"
down_revision: str | None = "20260529_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_engagement_log_entries_tenant_id", "engagement_log_entries", ["tenant_id"])
    op.create_index("idx_engagement_log_entries_engagement_id", "engagement_log_entries", ["engagement_id"])


def downgrade() -> None:
    op.drop_index("idx_engagement_log_entries_engagement_id", table_name="engagement_log_entries")
    op.drop_index("idx_engagement_log_entries_tenant_id", table_name="engagement_log_entries")
    op.drop_table("engagement_log_entries")
