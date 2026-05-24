"""Phase C inc 9.1 — email ingest events landing table.

# expand-contract: expand — one new table; no changes to existing tables.

Twin of the 9.2 meeting webhook landing pattern: a raw inbox for email
payloads. For now those payloads arrive via paste (IMAP/MBOX text); once
Gmail / M365 OAuth ships (deferred per ORCHESTRATOR D1), the OAuth-side
connector writes here with the same row shape.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0032"
down_revision: str | None = "20260613_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_ingest_events",
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
        sa.Column("external_message_id", sa.Text(), nullable=True),
        sa.Column("raw_payload", sa.Text(), nullable=False),
        sa.Column("parsed_subject", sa.Text(), nullable=True),
        sa.Column("parsed_from", sa.Text(), nullable=True),
        sa.Column(
            "parsed_to",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default=sa.text("ARRAY[]::text[]"),
        ),
        sa.Column("parsed_date", sa.TIMESTAMP(timezone=True), nullable=True),
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
        "idx_email_ingest_events_tenant_id",
        "email_ingest_events",
        ["tenant_id"],
    )
    op.create_index(
        "idx_email_ingest_events_engagement_id",
        "email_ingest_events",
        ["engagement_id"],
    )
    op.create_index(
        "idx_email_ingest_events_received_at",
        "email_ingest_events",
        ["received_at"],
    )
    op.create_index(
        "idx_email_ingest_events_source_external_id",
        "email_ingest_events",
        ["tenant_id", "source", "external_message_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_email_ingest_events_source_external_id",
        table_name="email_ingest_events",
    )
    op.drop_index(
        "idx_email_ingest_events_received_at",
        table_name="email_ingest_events",
    )
    op.drop_index(
        "idx_email_ingest_events_engagement_id",
        table_name="email_ingest_events",
    )
    op.drop_index(
        "idx_email_ingest_events_tenant_id",
        table_name="email_ingest_events",
    )
    op.drop_table("email_ingest_events")
