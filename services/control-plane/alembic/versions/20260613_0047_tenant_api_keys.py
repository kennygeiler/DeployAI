"""v2 Phase 4 — tenant_api_keys table for MCP inbound bearer auth.

# expand-contract: expand — new isolated table + index, no changes to
# existing rows or columns.

One row per minted API key. The raw secret is shown ONCE at creation and
never persisted; the row stores only an Argon2id hash of the raw key.
``engagement_id`` is nullable so future tenant-wide keys are possible,
though Phase 4 mints them with a single engagement scope. See
scope-v2 §8.4.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0047"
down_revision: str | None = "20260613_0046"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.create_table(
        "tenant_api_keys",
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
            nullable=True,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("hashed_secret", sa.Text(), nullable=False),
        sa.Column(
            "scopes",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY['read']::text[]"),
        ),
        sa.Column("last_used_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "name", name="uq_tenant_api_keys_tenant_name"),
    )
    op.create_index(
        "tenant_api_keys_active",
        "tenant_api_keys",
        ["hashed_secret"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    op.create_index(
        "tenant_api_keys_by_tenant",
        "tenant_api_keys",
        ["tenant_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.drop_index("tenant_api_keys_by_tenant", table_name="tenant_api_keys")
    op.drop_index("tenant_api_keys_active", table_name="tenant_api_keys")
    op.drop_table("tenant_api_keys")
