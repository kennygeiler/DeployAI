"""Per-guest demo sandbox marker on engagements (guest-sandbox wave).

# expand-contract: expand — one nullable column + partial index.

``engagements.demo_sandbox_at`` marks an engagement as a per-visitor demo
sandbox minted by ``POST /internal/v1/demo/session``. NULL means a real (or
seeded-fixture) engagement. The timestamp doubles as the reaper clock: each
demo mint deletes sandboxes older than 24h. A name suffix was rejected —
visitors would see it; the column is invisible in every read model.

The partial index covers both hot paths: the reaper's "older than" scan and
the guest list filter's ``demo_sandbox_at IS NULL OR id = :sandbox`` shape,
while costing nothing on the (vastly more common) non-sandbox rows.

Revision ID: 20260813_0062
Revises: 20260813_0061
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260813_0062"
down_revision: str | None = "20260813_0061"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """# expand-contract: expand"""
    # 0042 sets the database-level search_path to ag_catalog,"$user",public;
    # pin DDL to public like the surrounding migrations do.
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.add_column(
        "engagements",
        sa.Column("demo_sandbox_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.execute(
        "CREATE INDEX ix_engagements_demo_sandbox_at ON public.engagements (demo_sandbox_at) "
        "WHERE demo_sandbox_at IS NOT NULL"
    )


def downgrade() -> None:
    """# expand-contract: contract"""
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.execute("DROP INDEX IF EXISTS public.ix_engagements_demo_sandbox_at")
    op.drop_column("engagements", "demo_sandbox_at")
