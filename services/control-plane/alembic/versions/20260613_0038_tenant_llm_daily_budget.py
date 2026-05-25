"""Phase F2.b — tenant_llm_daily_budget: per-tenant daily LLM token cap.

# expand-contract: expand — one new table; no changes to existing tables.

Per ``docs/design/timeline-ledger.md`` §5.4 / §11 F2.b: LLM-assisted analyzers
must check + decrement a per-tenant daily token budget before any LLM call.
Default cap is 50,000 tokens/day; configurable later via Settings.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0038"
down_revision: str | None = "20260613_0037"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_llm_daily_budget",
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id"),
            nullable=False,
        ),
        sa.Column("usage_date", sa.Date(), nullable=False),
        sa.Column(
            "tokens_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "daily_cap",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("50000"),
        ),
        sa.PrimaryKeyConstraint("tenant_id", "usage_date"),
        sa.CheckConstraint("tokens_used >= 0", name="tenant_llm_budget_tokens_nonneg"),
        sa.CheckConstraint("daily_cap >= 0", name="tenant_llm_budget_cap_nonneg"),
    )


def downgrade() -> None:
    op.drop_table("tenant_llm_daily_budget")
