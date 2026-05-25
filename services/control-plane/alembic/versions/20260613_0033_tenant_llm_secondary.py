"""Phase D inc 1b — per-tenant LLM secondary provider for failover.

# expand-contract: expand — three nullable columns on tenant_llm_configs.

When a tenant sets a secondary provider/key/model in addition to the
primary, the agent factory composes a FailoverProvider; otherwise it
keeps returning the single-provider behavior. All three columns are
additive and nullable so the migration is reversible and safe to apply
on populated production rows.

UI surface (BFF + Settings picker) is a follow-up slice — this migration
is scaffold-only so the owner-credentialed wiring lands mechanically.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260613_0033"
down_revision: str | None = "20260613_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant_llm_configs",
        sa.Column("secondary_provider", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "tenant_llm_configs",
        sa.Column("secondary_api_key", sa.Text(), nullable=True),
    )
    op.add_column(
        "tenant_llm_configs",
        sa.Column("secondary_model_name", sa.String(length=200), nullable=True),
    )
    op.create_check_constraint(
        "ck_tenant_llm_configs_secondary_provider",
        "tenant_llm_configs",
        "secondary_provider IS NULL OR secondary_provider IN ('anthropic', 'openai', 'stub')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_tenant_llm_configs_secondary_provider", "tenant_llm_configs", type_="check")
    op.drop_column("tenant_llm_configs", "secondary_model_name")
    op.drop_column("tenant_llm_configs", "secondary_api_key")
    op.drop_column("tenant_llm_configs", "secondary_provider")
