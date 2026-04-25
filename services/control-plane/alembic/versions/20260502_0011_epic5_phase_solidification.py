"""Epic 5: deployment phase + solidification review queue (Stories 5.4, 5.5)."""

# expand

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260502_0011"
down_revision: str | None = "20260423_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_deployment_phases",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("phase", sa.Text(), nullable=False, server_default=sa.text("'P1_pre_engagement'")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_table(
        "phase_transition_proposals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=text("deployai_uuid_v7()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("from_phase", sa.Text(), nullable=False),
        sa.Column("to_phase", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("evidence_event_ids", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("proposer_agent", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("decided_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("decided_by_actor_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index("idx_phase_proposals_tenant", "phase_transition_proposals", ["tenant_id", "status"])
    op.create_table(
        "solidification_review_queue",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=text("deployai_uuid_v7()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("learning_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("solidified_learnings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default=sa.text("'open'")),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_solidif_review_tenant", "solidification_review_queue", ["tenant_id", "status"])


def downgrade() -> None:
    op.drop_index("idx_solidif_review_tenant", table_name="solidification_review_queue", if_exists=True)
    op.drop_table("solidification_review_queue")
    op.drop_index("idx_phase_proposals_tenant", table_name="phase_transition_proposals", if_exists=True)
    op.drop_table("phase_transition_proposals")
    op.drop_table("tenant_deployment_phases")
