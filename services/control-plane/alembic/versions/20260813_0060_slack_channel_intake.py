"""Slack channel-scoped intake (Wave 5 SL1) — mapping, staging, pending tables.

# expand-contract: expand — three new tables, no changes to existing ones.

Consent model: inviting the DeployAI bot to a Slack channel is the consent
boundary. A ``slack_channel_mappings`` row (channel → engagement) is the
strategist's explicit opt-in; only mapped channels' messages are ever
stored. ``slack_staging_messages`` accumulates raw message events for
mapped channels until the flush batches them into ``slack.thread``
canonical snapshot events. ``slack_pending_channels`` records only the
channel id + name (no message content) when the bot is invited to a
channel nobody has mapped yet, so the settings UI can offer it for
mapping without storing unconsented content.

RLS: same forced tenant policy as 0053/0058 on all three tables.

Revision ID: 20260813_0059
Revises: 20260813_0058
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260813_0060"
down_revision: str | None = "20260813_0059"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_MAPPINGS = "slack_channel_mappings"
_STAGING = "slack_staging_messages"
_PENDING = "slack_pending_channels"
_TABLES = (_MAPPINGS, _STAGING, _PENDING)


def _tenant_col() -> sa.Column[object]:
    return sa.Column(
        "tenant_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )


def upgrade() -> None:
    """# expand-contract: expand"""
    # 0042 sets the database-level search_path to ag_catalog,"$user",public;
    # pin DDL to public like the surrounding migrations do.
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.create_table(
        _MAPPINGS,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _tenant_col(),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("channel_name", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_by", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("revoked_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index(f"ix_{_MAPPINGS}_tenant_id", _MAPPINGS, ["tenant_id"])
    # One *active* mapping per channel; revoked rows stay as history.
    op.execute(
        f"CREATE UNIQUE INDEX uq_{_MAPPINGS}_active "
        f"ON public.{_MAPPINGS} (tenant_id, channel_id) WHERE revoked_at IS NULL"
    )

    op.create_table(
        _STAGING,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _tenant_col(),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("message_ts", sa.Text(), nullable=False),
        sa.Column("thread_ts", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("text", sa.Text(), nullable=False, server_default=""),
        sa.Column("team_id", sa.Text(), nullable=False, server_default=""),
        sa.Column("occurred_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "received_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("flushed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        # Slack event re-delivery lands on this constraint (at-most-once staging).
        sa.UniqueConstraint("tenant_id", "channel_id", "message_ts", name=f"uq_{_STAGING}_msg"),
    )
    op.create_index(f"ix_{_STAGING}_tenant_id", _STAGING, ["tenant_id"])
    op.execute(
        f"CREATE INDEX ix_{_STAGING}_unflushed ON public.{_STAGING} (tenant_id, channel_id) WHERE flushed_at IS NULL"
    )

    op.create_table(
        _PENDING,
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        _tenant_col(),
        sa.Column("channel_id", sa.Text(), nullable=False),
        sa.Column("channel_name", sa.Text(), nullable=False, server_default=""),
        sa.Column(
            "first_seen_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.UniqueConstraint("tenant_id", "channel_id", name=f"uq_{_PENDING}_channel"),
    )
    op.create_index(f"ix_{_PENDING}_tenant_id", _PENDING, ["tenant_id"])

    # Same RLS shape as 0053 (tenant-scoped tables).
    for table in _TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        op.execute(f"DROP POLICY IF EXISTS tenant_rls_{table} ON public.{table}")
        op.execute(
            f"""
            CREATE POLICY tenant_rls_{table}
                ON public.{table}
                USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
                WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            """
        )
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO deployai_app")


def downgrade() -> None:
    """# expand-contract: contract"""
    op.execute("SET LOCAL search_path = public, ag_catalog")
    for table in _TABLES:
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON public.{table} FROM deployai_app")
    op.drop_index(f"ix_{_PENDING}_tenant_id", table_name=_PENDING)
    op.drop_table(_PENDING)
    op.execute(f"DROP INDEX IF EXISTS public.ix_{_STAGING}_unflushed")
    op.drop_index(f"ix_{_STAGING}_tenant_id", table_name=_STAGING)
    op.drop_table(_STAGING)
    op.execute(f"DROP INDEX IF EXISTS public.uq_{_MAPPINGS}_active")
    op.drop_index(f"ix_{_MAPPINGS}_tenant_id", table_name=_MAPPINGS)
    op.drop_table(_MAPPINGS)
