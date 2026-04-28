"""Epic 11.2 — edge agent device registration (Ed25519 public key per tenant).

# expand-contract: expand
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260526_0014"
down_revision: str | None = "20260504_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "edge_agents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=text("deployai_uuid_v7()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("device_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("public_key_ed25519", sa.LargeBinary(length=32), nullable=False),
        sa.Column("registered_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("idx_edge_agents_tenant", "edge_agents", ["tenant_id"])
    op.create_index(
        "uq_edge_agents_tenant_device",
        "edge_agents",
        ["tenant_id", "device_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_edge_agents_tenant_device", table_name="edge_agents")
    op.drop_index("idx_edge_agents_tenant", table_name="edge_agents")
    op.drop_table("edge_agents")
