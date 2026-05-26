"""v2 Phase 2 — agent_audit_traces table for Agent Kenny v2 turn audit.

# expand-contract: expand — new isolated table + index, no changes to
# existing rows or columns.

One row per Kenny v2 chat turn, capturing citation totals, tool calls,
revision attempts, adversarial concerns and the final reply text so the
Phase 6 hallucination dashboard can compute trend metrics without a
follow-up join through every ledger row. See scope-v2 §7.4.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0045"
down_revision: str | None = "20260613_0044"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.create_table(
        "agent_audit_traces",
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
        sa.Column(
            "turn_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            unique=True,
        ),
        sa.Column("total_citations", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("verified_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("unverified_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "cross_engagement_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("external_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("revision_attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "adversarial_concerns_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("tool_calls_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "duration_ms",
            sa.Float(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("final_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index(
        "agent_audit_traces_by_engagement",
        "agent_audit_traces",
        ["tenant_id", "engagement_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.drop_index("agent_audit_traces_by_engagement", table_name="agent_audit_traces")
    op.drop_table("agent_audit_traces")
