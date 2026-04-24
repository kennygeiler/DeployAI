"""Epic 3: canonical ingestion_dedup_key (FR18) + ingestion_runs (Story 3-8)."""

# expand-contract: expand

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

revision: str = "20260501_0009"
down_revision: str | None = "20260430_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "canonical_memory_events",
        sa.Column("ingestion_dedup_key", sa.Text(), nullable=True),
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_cme_tenant_ingest_dedup
        ON canonical_memory_events (tenant_id, ingestion_dedup_key)
        WHERE ingestion_dedup_key IS NOT NULL
        """
    )
    op.create_table(
        "ingestion_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=text("deployai_uuid_v7()")),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("integration", sa.Text(), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'running'")),
        sa.Column("events_written", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error_summary", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.create_index("idx_ingestion_runs_tenant_started", "ingestion_runs", ["tenant_id", "started_at"])


def downgrade() -> None:
    op.drop_index("idx_ingestion_runs_tenant_started", table_name="ingestion_runs", if_exists=True)
    op.drop_table("ingestion_runs")
    op.execute("DROP INDEX IF EXISTS uq_cme_tenant_ingest_dedup")
    op.drop_column("canonical_memory_events", "ingestion_dedup_key")
