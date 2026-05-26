"""Phase G1.a — Mr. Oracle chat: oracle_conversations + oracle_chat_turns.

# expand-contract: expand — two new tables; no changes to existing tables.

Per ``docs/design/post-f-polish.md`` §8. One conversation per
(tenant, engagement, actor user); chat turns are append-only with the
context event ids carried alongside each turn so the ledger dual-emit
in the chat service can wire ``caused_by`` to the upstream causal chain.
Composite FK on ``(tenant_id, engagement_id)`` uses the unique constraint
F3.a added to ``engagements``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0040"
down_revision: str | None = "20260613_0039"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "oracle_conversations",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("engagement_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "last_turn_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "engagement_id"],
            ["engagements.tenant_id", "engagements.id"],
            ondelete="CASCADE",
            name="fk_oracle_conversations_engagement_tenant",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "engagement_id",
            "actor_user_id",
            name="uq_oracle_conversations_tenant_engagement_actor",
        ),
    )
    op.create_table(
        "oracle_chat_turns",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("oracle_conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "context_event_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "tokens_used",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("role IN ('user', 'oracle')", name="oracle_chat_turns_role_enum"),
    )
    op.create_index(
        "ix_oracle_turns_convo_created",
        "oracle_chat_turns",
        ["conversation_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_oracle_turns_convo_created", table_name="oracle_chat_turns")
    op.drop_table("oracle_chat_turns")
    op.drop_table("oracle_conversations")
