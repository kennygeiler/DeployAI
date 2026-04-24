# expand-contract: expand (Story 2-6/2-7) — integration registry + break-glass session rows.

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "20260428_0006"
down_revision: str | None = "20260426_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "integrations",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("state", sa.Text(), server_default=sa.text("'active'"), nullable=False),
        sa.Column("config", JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("disabled_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("state IN ('active', 'disabled')", name="ck_integrations_state"),
        sa.ForeignKeyConstraint(["tenant_id"], ["app_tenants.id"], name="fk_integrations_tenant", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id", name="pk_integrations"),
    )
    op.create_index("ix_integrations_tenant_id", "integrations", ["tenant_id"])

    op.create_table(
        "break_glass_sessions",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("initiator_sub", sa.Text(), nullable=False),
        sa.Column("approver_sub", sa.Text(), nullable=True),
        sa.Column("requested_scope", sa.Text(), server_default=sa.text("'tenant_data_read'"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("requested_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("approved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("audit_transcript_ref", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "status IN ('requested', 'approved', 'active', 'expired', 'denied')",
            name="ck_break_glass_sessions_status",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["app_tenants.id"],
            name="fk_break_glass_sessions_tenant",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_break_glass_sessions"),
    )
    op.create_index("ix_break_glass_sessions_tenant", "break_glass_sessions", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_break_glass_sessions_tenant", table_name="break_glass_sessions")
    op.drop_table("break_glass_sessions")
    op.drop_index("ix_integrations_tenant_id", table_name="integrations")
    op.drop_table("integrations")
