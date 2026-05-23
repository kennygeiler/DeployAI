"""Sprint 1 — per-tenant LLM provider configuration.

Customers running DeployAI self-hosted set their provider + model + API
key at runtime via the Settings UI instead of editing the compose env
+ restarting. One row per tenant; if no row exists, the agent factory
falls back to env defaults (existing dev behavior).

API keys are stored plaintext in the database. Acceptable for a
self-hosted single-team deployment: the customer owns the DB and the
host. For shared / multi-tenant hosting, encrypt at rest with a vault
or per-row Fernet — out of scope for v1.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0025"
down_revision: str | None = "20260605_0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_llm_configs",
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
            unique=True,
        ),
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=True),
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
            "provider IN ('anthropic', 'openai', 'stub')",
            name="ck_tenant_llm_configs_provider",
        ),
    )


def downgrade() -> None:
    op.drop_table("tenant_llm_configs")
