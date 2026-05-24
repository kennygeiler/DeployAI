"""Sprint 6 inc 2 — tenant-scoped custom engagement-member roles.

A healthcare team adds ``clinical_lead``; a B2B SaaS team adds
``sales_engineer``. Custom roles extend the baked-in trio (``fde``,
``deployment_strategist``, ``biz_dev``) without a schema change. ``name``
is the slug (lowercase + underscores); ``label`` is the human display;
``description`` is an optional hint.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0030"
down_revision: str | None = "20260613_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "tenant_member_roles",
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
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("tenant_id", "name", name="uq_tenant_member_roles_tenant_name"),
    )
    op.create_index("idx_tenant_member_roles_tenant_id", "tenant_member_roles", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("tenant_member_roles")
