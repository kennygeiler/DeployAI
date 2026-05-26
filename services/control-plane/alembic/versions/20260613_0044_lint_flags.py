"""v2 Phase 0.6 — lint_flags table for synthesis substrate integrity scanner.

# expand-contract: expand — new isolated table + indexes, no changes to
# existing rows or columns.

Flags-only table populated by the lint worker (``control_plane.workers.wiki_lint``)
when it scans matrix_nodes / matrix_insights / matrix_edges for integrity
issues (contradictions, stale claims, orphan references, missing/broken
cites). The worker NEVER mutates curated content; strategists and Kenny
himself resolve flagged issues out-of-band by setting ``resolved_at``.

See scope-v2 §4 and ethos §3.1 (lint pass from Karpathy's wiki gist).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0044"
down_revision: str | None = "20260613_0043"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0042 sets the database-level search_path to ag_catalog,"$user",public.
    # Pin this migration's DDL to public so the new table lands where every
    # other DeployAI table lives.
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.create_table(
        "lint_flags",
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
            nullable=True,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target_kind", sa.Text(), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "flagged_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('contradiction','stale','orphan','missing_cite','broken_cite')",
            name="lint_flags_kind_check",
        ),
    )
    op.create_index(
        "lint_flags_open_by_engagement",
        "lint_flags",
        ["tenant_id", "engagement_id", "kind"],
        postgresql_where=sa.text("resolved_at IS NULL"),
    )
    op.create_index(
        "lint_flags_target",
        "lint_flags",
        ["target_kind", "target_id"],
    )


def downgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.drop_table("lint_flags")
