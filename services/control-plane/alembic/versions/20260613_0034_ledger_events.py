"""Phase F1.a — ledger_events: append-only causal timeline base table.

# expand-contract: expand — one new table; no changes to existing tables.

Per ``docs/design/timeline-ledger.md`` §3.1: a tenant-scoped, append-only log
of "something happened" rows that consolidates every existing surface
(email_ingest_events, meeting_webhook_events, matrix_proposals state
transitions, matrix_nodes/edges CRUD, audit emits, oracle insights) into one
queryable timeline. Sibling migrations 0035/0036/0037 add cause/affect edges
and derived temporal_insights on top.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0034"
down_revision: str | None = "20260613_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ledger_events",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id"),
            nullable=True,
        ),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "recorded_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("actor_kind", sa.String(length=40), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=True),
        sa.Column("source_kind", sa.String(length=80), nullable=False),
        sa.Column("source_ref", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column(
            "detail",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "char_length(summary) BETWEEN 1 AND 500",
            name="ledger_summary_len",
        ),
    )
    op.create_index(
        "ix_ledger_tenant_occurred",
        "ledger_events",
        ["tenant_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_ledger_engagement_occurred",
        "ledger_events",
        ["engagement_id", sa.text("occurred_at DESC")],
        postgresql_where=sa.text("engagement_id IS NOT NULL"),
    )
    op.create_index("ix_ledger_source_kind", "ledger_events", ["source_kind"])
    op.create_index("ix_ledger_actor", "ledger_events", ["actor_kind", "actor_id"])
    op.create_index(
        "ix_ledger_detail_gin",
        "ledger_events",
        ["detail"],
        postgresql_using="gin",
        postgresql_ops={"detail": "jsonb_path_ops"},
    )


def downgrade() -> None:
    op.drop_index("ix_ledger_detail_gin", table_name="ledger_events")
    op.drop_index("ix_ledger_actor", table_name="ledger_events")
    op.drop_index("ix_ledger_source_kind", table_name="ledger_events")
    op.drop_index("ix_ledger_engagement_occurred", table_name="ledger_events")
    op.drop_index("ix_ledger_tenant_occurred", table_name="ledger_events")
    op.drop_table("ledger_events")
