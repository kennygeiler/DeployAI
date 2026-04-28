"""Epic 9 pilot — durable strategist queues (action, validation, solidification).

# expand-contract: expand — tables scoped by tenant_id; application enforces tenant filter on internal API.

"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260527_0015"
down_revision: str | None = "20260526_0014"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strategist_action_queue_items",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("priority", sa.Text(), nullable=False),
        sa.Column("phase", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("claimed_by", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("evidence_node_ids", postgresql.ARRAY(sa.Text()), nullable=False, server_default=sa.text("'{}'::text[]")),
        sa.Column("resolution_reason", sa.Text(), nullable=True),
        sa.Column("evidence_event_ids", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_strategist_action_queue_tenant", "strategist_action_queue_items", ["tenant_id"])
    op.create_index("idx_strategist_action_queue_tenant_status", "strategist_action_queue_items", ["tenant_id", "status"])

    op.create_table(
        "strategist_validation_queue_items",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("proposed_fact", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_strategist_validation_queue_tenant", "strategist_validation_queue_items", ["tenant_id"])
    op.create_index("idx_strategist_validation_queue_tenant_state", "strategist_validation_queue_items", ["tenant_id", "state"])

    op.create_table(
        "strategist_solidification_queue_items",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("proposed_fact", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_strategist_solidification_queue_tenant", "strategist_solidification_queue_items", ["tenant_id"])
    op.create_index(
        "idx_strategist_solidification_queue_tenant_state",
        "strategist_solidification_queue_items",
        ["tenant_id", "state"],
    )


def downgrade() -> None:
    op.drop_index("idx_strategist_solidification_queue_tenant_state", table_name="strategist_solidification_queue_items")
    op.drop_index("idx_strategist_solidification_queue_tenant", table_name="strategist_solidification_queue_items")
    op.drop_table("strategist_solidification_queue_items")

    op.drop_index("idx_strategist_validation_queue_tenant_state", table_name="strategist_validation_queue_items")
    op.drop_index("idx_strategist_validation_queue_tenant", table_name="strategist_validation_queue_items")
    op.drop_table("strategist_validation_queue_items")

    op.drop_index("idx_strategist_action_queue_tenant_status", table_name="strategist_action_queue_items")
    op.drop_index("idx_strategist_action_queue_tenant", table_name="strategist_action_queue_items")
    op.drop_table("strategist_action_queue_items")
