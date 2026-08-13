"""Wave 5 GA1 — gap_ask_dismissals: durable dismiss/snooze for "Kenny asks".

# expand-contract: expand — one new table, no existing shapes touched.

Asks are recomputed deterministically on every read (services.gap_detection);
only the user's dismiss/snooze decision persists here, keyed by the ask's
deterministic id so it survives recomputes. ``snooze_until IS NULL`` means a
permanent dismissal; a set value hides the ask until that moment.

Revision ID: 20260813_0059
Revises: 20260813_0058
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260813_0059"
down_revision: str | None = "20260813_0058"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "gap_ask_dismissals"


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
        sa.Column("ask_id", sa.Text(), nullable=False),
        sa.Column("dismissed_by", sa.Text(), nullable=True),
        sa.Column(
            "dismissed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("snooze_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "engagement_id",
            "ask_id",
            name="uq_gap_ask_dismissals_tenant_engagement_ask",
        ),
    )
    op.create_index("idx_gap_ask_dismissals_engagement", TABLE, ["tenant_id", "engagement_id"])

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
    op.drop_index("idx_gap_ask_dismissals_engagement", table_name=TABLE)
    op.drop_table(TABLE)
