"""Phase 7 (increment 7.2) — matrix_insights.

# expand-contract: expand — one new table; no changes to existing tables.

Matrix insights are observations produced by the Oracle (per-engagement) and
Master Strategist (cross-engagement) synthesis agents. An insight cites the
matrix nodes / edges / canonical events it was derived from; the user can
dismiss or resolve it. Unlike matrix_proposals, insights do not mutate the
matrix on accept — they are observations, not graph edits.

``engagement_id`` is nullable: null = tenant-scoped (Master Strategist).
``dedup_key`` is the idempotency anchor — refresh upserts in place, so
re-running the agent does not produce duplicate cards. See the
[design record](../../../../docs/product/synthesis-agents.md) §7, §11.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260605_0024"
down_revision: str | None = "20260604_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "matrix_insights",
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
            # Nullable — tenant-scoped insights (Master Strategist) leave this null.
            nullable=True,
        ),
        sa.Column("agent", sa.Text(), nullable=False),  # 'oracle' | 'master_strategist'
        sa.Column("insight_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),  # 'low' | 'medium' | 'high'
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "citation_node_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "citation_edge_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "citation_event_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column("dedup_key", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column(
            "input_hash",
            sa.Text(),
            # Hash of the predicate inputs. If unchanged on refresh, skip the LLM
            # call and leave the existing title/body untouched. Design §11.
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_by", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "agent IN ('oracle', 'master_strategist')",
            name="ck_matrix_insights_agent",
        ),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high')",
            name="ck_matrix_insights_severity",
        ),
        sa.CheckConstraint(
            "status IN ('open', 'dismissed', 'resolved')",
            name="ck_matrix_insights_status",
        ),
    )
    op.create_index(
        "idx_matrix_insights_engagement_status",
        "matrix_insights",
        ["tenant_id", "engagement_id", "status"],
    )
    op.create_index(
        "idx_matrix_insights_tenant_agent_status",
        "matrix_insights",
        ["tenant_id", "agent", "status"],
    )
    op.create_index(
        "uq_matrix_insights_dedup_key",
        "matrix_insights",
        ["dedup_key"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("matrix_insights")
