"""Epic 10 — private override annotations + strategist personal-activity log.

# expand-contract: expand
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260504_0013"
down_revision: str | None = "20260503_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "private_override_annotations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=text("deployai_uuid_v7()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "override_event_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("canonical_memory_events.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("author_actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("wrapped_dek", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_private_override_annotations_tenant_override",
        "private_override_annotations",
        ["tenant_id", "override_event_id"],
        unique=True,
    )
    op.create_table(
        "strategist_activity_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=text("deployai_uuid_v7()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("detail", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ref_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_strategist_activity_tenant_actor", "strategist_activity_events", ["tenant_id", "actor_id"])
    op.create_index("idx_strategist_activity_created", "strategist_activity_events", ["tenant_id", "created_at"])


def downgrade() -> None:
    op.drop_index("idx_strategist_activity_created", table_name="strategist_activity_events")
    op.drop_index("idx_strategist_activity_tenant_actor", table_name="strategist_activity_events")
    op.drop_table("strategist_activity_events")
    op.drop_index("idx_private_override_annotations_tenant_override", table_name="private_override_annotations")
    op.drop_table("private_override_annotations")
