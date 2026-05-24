"""Per-tenant overrides for the Cartographer / Oracle / Master Strategist system prompts."""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0026"
down_revision: str | None = "20260613_0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_agent_prompts",
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
        sa.Column("agent_name", sa.Text(), nullable=False),
        sa.Column("prompt_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "agent_name IN ('cartographer', 'oracle', 'master_strategist')",
            name="ck_tenant_agent_prompts_agent_name",
        ),
        sa.UniqueConstraint("tenant_id", "agent_name", name="uq_tenant_agent_prompts_tenant_agent"),
    )


def downgrade() -> None:
    op.drop_table("tenant_agent_prompts")
