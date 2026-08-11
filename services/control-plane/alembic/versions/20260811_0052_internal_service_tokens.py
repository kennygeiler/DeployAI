"""Pilot-refresh A4 — internal_service_tokens: per-tenant internal-API credentials.

# expand-contract: expand — one new table; no changes to existing tables.

Replaces the single global ``X-DeployAI-Internal-Key`` (which let any key
holder name any ``tenant_id``) with tenant-bound service tokens. The raw
secret is shown once at mint time; only its SHA-256 hex digest is stored
(same posture as ``app_tenants.scim_bearer_token_hash``). Verification and
the tenant-match rule live in ``control_plane/config/internal_auth.py``.

This table is deliberately **not** RLS-scoped: token lookup happens during
authentication, before any tenant scope exists — a tenant policy here would
be a chicken-and-egg deadlock. It is an infra/auth table like ``app_tenants``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260811_0052"
down_revision: str | None = "20260811_0051"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "internal_service_tokens"


def upgrade() -> None:
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("hashed_key", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "name", name="uq_internal_service_tokens_tenant_name"),
    )
    # Auth hot path: digest lookup over active tokens only.
    op.create_index(
        "internal_service_tokens_active",
        TABLE,
        ["hashed_key"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "internal_service_tokens_by_tenant",
        TABLE,
        ["tenant_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("internal_service_tokens_by_tenant", table_name=TABLE)
    op.drop_index("internal_service_tokens_active", table_name=TABLE)
    op.drop_table(TABLE)
