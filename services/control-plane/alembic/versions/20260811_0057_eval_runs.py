"""Wave 4 showcase G8 — eval_runs: longitudinal eval-quality history.

# expand-contract: expand — one new table; no changes to existing tables.

Each row is one execution of the golden-question eval runner
(``tests/golden/agent_kenny/runner.py``). The summary metrics are lifted
into typed columns so the admin dashboard can chart trends cheaply; the
runner's full report JSON is kept verbatim in ``report`` for drill-down.

This table is deliberately **platform-level** — it has NO ``tenant_id``.
Eval runs measure the product (Agent Kenny's quality over time), not any
tenant's data; they run in CI/local against synthetic fixtures. It is
therefore documented in the RLS catalog test's exemption list
(``tests/integration/test_rls_expansion.py``) alongside ``app_tenants``
and ``internal_service_tokens``. Access is gated by the global internal
key (``require_internal``) at the route layer.

Revision ID: 20260811_0057
Revises: 20260811_0056
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260811_0057"
down_revision: str | None = "20260811_0056"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "eval_runs"


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
            "run_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("runtime", sa.Text(), nullable=True),
        sa.Column("question_count", sa.Integer(), nullable=False),
        sa.Column("pass_rate", sa.Double(), nullable=False),
        sa.Column("idk_rate", sa.Double(), nullable=False),
        sa.Column("hallucination_rate", sa.Double(), nullable=False),
        sa.Column("cross_engagement_leak_count", sa.Integer(), nullable=False),
        sa.Column("p50_ms", sa.Double(), nullable=True),
        sa.Column("p95_ms", sa.Double(), nullable=True),
        sa.Column(
            "report",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.CheckConstraint(
            "source IN ('ci','local','longitudinal')",
            name="ck_eval_runs_source",
        ),
    )
    # Trend queries read newest-first.
    op.create_index("ix_eval_runs_run_at", TABLE, [sa.text("run_at DESC")])

    # No RLS: platform-level ops data, no tenant_id (see module docstring).
    # The app role still needs plain table privileges to serve the admin
    # routes. Runs are append-only — no UPDATE/DELETE grant.
    op.execute(f"GRANT SELECT, INSERT ON public.{TABLE} TO deployai_app")


def downgrade() -> None:
    """# expand-contract: contract"""
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.execute(f"REVOKE SELECT, INSERT ON public.{TABLE} FROM deployai_app")
    op.drop_index("ix_eval_runs_run_at", table_name=TABLE)
    op.drop_table(TABLE)
