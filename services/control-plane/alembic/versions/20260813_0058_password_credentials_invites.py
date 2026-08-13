"""Self-serve accounts — native password credentials + single-use invites.

# expand-contract: expand — two nullable columns on ``app_users``, one new table.

Why columns on ``app_users`` instead of a separate ``user_credentials`` table:
a user row is already the join point for every auth method this schema knows
(``entra_sub`` for OIDC, ``scim_external_id`` for SCIM) — each method is a
nullable column on the same row, 1:1 by construction. A password credential
follows the exact same shape; a side table would add a join to the hot login
path and a second place to enforce the 1:1 without buying anything (there is
no multi-credential-per-method requirement). Both columns are nullable so
SSO/SCIM-only users are untouched.

``user_invites`` stores SHA-256 token digests only (the raw invite token
lives in the join URL the admin copies; a DB leak cannot redeem invites).
RLS: same forced tenant policy as every table in 0053 — but like
``app_users`` (whose email lookup at login runs unscoped), the accept path
resolves ``token_hash`` before any tenant scope exists, which works because
the app's runtime role is not RLS-subject; ``deployai_app`` (the RLS-subject
role integration tests use) stays fully tenant-fenced.

Revision ID: 20260813_0058
Revises: 20260811_0057
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260813_0058"
down_revision: str | None = "20260811_0057"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "user_invites"


def upgrade() -> None:
    """# expand-contract: expand"""
    # 0042 sets the database-level search_path to ag_catalog,"$user",public;
    # pin DDL to public like the surrounding migrations do.
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.add_column("app_users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column(
        "app_users",
        sa.Column("password_updated_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    # Login resolves the credentialed row by lowercased email; partial index
    # keeps SSO/SCIM-only rows (password_hash IS NULL) out of it.
    op.execute(
        "CREATE INDEX ix_app_users_email_password ON public.app_users (lower(email)) WHERE password_hash IS NOT NULL"
    )

    op.create_table(
        TABLE,
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
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False, unique=True),
        sa.Column("invited_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("accepted_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.create_index("ix_user_invites_tenant_id", TABLE, ["tenant_id"])

    # Same RLS shape as 0053 (tenant-scoped table).
    op.execute(f"ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{TABLE} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_rls_{TABLE} ON public.{TABLE}")
    op.execute(
        f"""
        CREATE POLICY tenant_rls_{TABLE}
            ON public.{TABLE}
            USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{TABLE} TO deployai_app")


def downgrade() -> None:
    """# expand-contract: contract"""
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON public.{TABLE} FROM deployai_app")
    op.drop_index("ix_user_invites_tenant_id", table_name=TABLE)
    op.drop_table(TABLE)
    op.execute("DROP INDEX IF EXISTS public.ix_app_users_email_password")
    op.drop_column("app_users", "password_updated_at")
    op.drop_column("app_users", "password_hash")
