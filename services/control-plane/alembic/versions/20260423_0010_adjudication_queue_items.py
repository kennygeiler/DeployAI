"""Epic 4 Story 4-7: adjudication queue for human review of replay-parity items."""

# expand

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260423_0010"
down_revision: str | None = "20260501_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "adjudication_queue_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=text("deployai_uuid_v7()")),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("query_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_adjudication_queue_items_tenant", "adjudication_queue_items", ["tenant_id"])
    op.create_index("idx_adjudication_queue_items_query_id", "adjudication_queue_items", ["query_id"])
    op.create_index("idx_adjudication_queue_items_status", "adjudication_queue_items", ["status"])


def downgrade() -> None:
    op.drop_index("idx_adjudication_queue_items_status", table_name="adjudication_queue_items", if_exists=True)
    op.drop_index("idx_adjudication_queue_items_query_id", table_name="adjudication_queue_items", if_exists=True)
    op.drop_index("idx_adjudication_queue_items_tenant", table_name="adjudication_queue_items", if_exists=True)
    op.drop_table("adjudication_queue_items")
