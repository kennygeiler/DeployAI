"""Phase 1 — engagements + engagement_members.

# expand-contract: expand — two new tables; no changes to existing tables.

Introduces the engagement entity: a tenant is the team, an engagement is one
customer deployment it runs. ``engagement_members`` links users to an
engagement with a role. Both tables are scoped by ``tenant_id``; the internal
API enforces the tenant filter (same posture as ``20260527_0015`` strategist
queues — no RLS on internal-API operational tables). See
``docs/product/deployai-source-of-truth-spec.md`` section 16 (Phase 1).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260528_0016"
down_revision: str | None = "20260527_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engagements",
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("customer_account", sa.Text(), nullable=True),
        sa.Column("current_phase", sa.Text(), nullable=False, server_default="P1_pre_engagement"),
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_engagements_tenant_id", "engagements", ["tenant_id"])

    op.create_table(
        "engagement_members",
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
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("engagement_id", "user_id", name="uq_engagement_members_engagement_id_user_id"),
    )
    op.create_index("idx_engagement_members_tenant_id", "engagement_members", ["tenant_id"])
    op.create_index("idx_engagement_members_engagement_id", "engagement_members", ["engagement_id"])
    op.create_index("idx_engagement_members_user_id", "engagement_members", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_engagement_members_user_id", table_name="engagement_members")
    op.drop_index("idx_engagement_members_engagement_id", table_name="engagement_members")
    op.drop_index("idx_engagement_members_tenant_id", table_name="engagement_members")
    op.drop_table("engagement_members")

    op.drop_index("idx_engagements_tenant_id", table_name="engagements")
    op.drop_table("engagements")
