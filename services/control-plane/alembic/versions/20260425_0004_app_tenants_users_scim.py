# expand-contract: expand (Story 2-3) — app identity + SCIM; additive only.

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "20260425_0004"
down_revision: str | None = "20260424_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "app_tenants",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("scim_bearer_token_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_app_tenants"),
    )
    op.create_index("idx_app_tenants_scim_bearer", "app_tenants", ["scim_bearer_token_hash"], unique=True)

    op.create_table(
        "app_users",
        sa.Column("id", UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", UUID(as_uuid=True), nullable=False),
        sa.Column("scim_external_id", sa.Text(), nullable=True),
        sa.Column("user_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("given_name", sa.Text(), nullable=True),
        sa.Column("family_name", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("roles", JSONB(), nullable=True),
        sa.Column("entra_sub", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"],
            ["app_tenants.id"],
            name="fk_app_users_tenant_id_app_tenants",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_app_users"),
    )
    op.create_index("idx_app_users_tenant_user_name", "app_users", ["tenant_id", "user_name"], unique=True)
    op.create_index(
        "uq_app_users_tenant_scim_external",
        "app_users",
        ["tenant_id", "scim_external_id"],
        unique=True,
        postgresql_where=sa.text("scim_external_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_app_users_tenant_scim_external", table_name="app_users")
    op.drop_index("idx_app_users_tenant_user_name", table_name="app_users")
    op.drop_table("app_users")
    op.drop_index("idx_app_tenants_scim_bearer", table_name="app_tenants")
    op.drop_table("app_tenants")
