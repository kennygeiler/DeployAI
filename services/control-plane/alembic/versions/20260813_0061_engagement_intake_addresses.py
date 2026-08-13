"""Inbound engagement email — per-engagement intake addresses (Wave 5 IN1).

# expand-contract: expand — one new table.

``engagement_intake_addresses`` maps an email local part
(``<slug>-<token>@<intake domain>``) to one engagement. Addresses are minted
lazily on first read and revoked (not deleted) on regenerate, so a webhook
delivery to a stale address can still be recognized as "revoked" and dropped
without leaking validity. The partial unique index enforces at most one
*active* address per engagement; revoked rows accumulate as history.

``local_part`` is globally unique: the webhook resolves it without knowing
the tenant, exactly like ``user_invites.token_hash`` resolves before tenant
scope exists — the app's runtime role is not RLS-subject, while
``deployai_app`` (the RLS-subject role integration tests use) stays fully
tenant-fenced by the same forced policy shape as 0053/0058.

Revision ID: 20260813_0059
Revises: 20260813_0058
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260813_0061"
down_revision: str | None = "20260813_0060"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "engagement_intake_addresses"


def upgrade() -> None:
    """# expand-contract: expand"""
    # 0042 sets the database-level search_path to ag_catalog,"$user",public;
    # pin DDL to public like the surrounding migrations do.
    op.execute("SET LOCAL search_path = public, ag_catalog")

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
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("local_part", sa.Text(), nullable=False, unique=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(f"ix_{TABLE}_tenant_id", TABLE, ["tenant_id"])
    # One ACTIVE address per engagement; revoked rows are history.
    op.execute(
        f"CREATE UNIQUE INDEX uq_{TABLE}_active_engagement ON public.{TABLE} (engagement_id) WHERE revoked_at IS NULL"
    )

    # Same RLS shape as 0053/0058 (tenant-scoped table).
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
    op.execute(f"DROP INDEX IF EXISTS public.uq_{TABLE}_active_engagement")
    op.drop_index(f"ix_{TABLE}_tenant_id", table_name=TABLE)
    op.drop_table(TABLE)
