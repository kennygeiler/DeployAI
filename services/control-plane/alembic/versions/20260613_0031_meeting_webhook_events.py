"""Phase C inc 9.2 — meeting webhook events ingress table.

# expand-contract: expand — one new table; no changes to existing tables.

Mirrors the D1 (Phase C inc 9.1) email-paste landing pattern: a raw inbox
for meeting payloads delivered by an as-yet-unbuilt OAuth flow. Webhook
receivers (Zoom-style) and manual transcript pastes write here first;
later increments fold processed rows into canonical memory + engagements.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0031"
down_revision: str | None = "20260613_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "meeting_webhook_events",
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
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("external_event_id", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "received_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("processed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
    )
    op.create_index(
        "idx_meeting_webhook_events_tenant_id",
        "meeting_webhook_events",
        ["tenant_id"],
    )
    op.create_index(
        "idx_meeting_webhook_events_engagement_id",
        "meeting_webhook_events",
        ["engagement_id"],
    )
    op.create_index(
        "idx_meeting_webhook_events_received_at",
        "meeting_webhook_events",
        ["received_at"],
    )
    op.create_index(
        "idx_meeting_webhook_events_source_external_id",
        "meeting_webhook_events",
        ["tenant_id", "source", "external_event_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_meeting_webhook_events_source_external_id",
        table_name="meeting_webhook_events",
    )
    op.drop_index(
        "idx_meeting_webhook_events_received_at",
        table_name="meeting_webhook_events",
    )
    op.drop_index(
        "idx_meeting_webhook_events_engagement_id",
        table_name="meeting_webhook_events",
    )
    op.drop_index(
        "idx_meeting_webhook_events_tenant_id",
        table_name="meeting_webhook_events",
    )
    op.drop_table("meeting_webhook_events")
