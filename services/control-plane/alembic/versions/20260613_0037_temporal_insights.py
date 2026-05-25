"""Phase F1.a — temporal_insights: derived time-window insights.

# expand-contract: expand — one new table; no changes to existing tables.

Per ``docs/design/timeline-ledger.md`` §3.4: a distinct table from the
existing ``matrix_insights`` (which is Oracle / Master-Strategist
*current-state* output). Temporal insights are produced by analyzers that
read the ledger over a bounded window — velocity, drift, pattern signals —
and cite the originating events via ``evidence_event_ids``. Sibling slice
F1.c ships the first four analyzers + the read API.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0037"
down_revision: str | None = "20260613_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "temporal_insights",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("app_tenants.id"),
            nullable=False,
        ),
        sa.Column(
            "engagement_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("engagements.id"),
            nullable=True,
        ),
        sa.Column("insight_kind", sa.String(length=80), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("narrative", sa.Text(), nullable=False),
        sa.Column("window_start", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("window_end", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column(
            "evidence_event_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=False,
            server_default=sa.text("'{}'::uuid[]"),
        ),
        sa.Column(
            "metrics",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "status",
            sa.String(length=16),
            nullable=False,
            server_default=sa.text("'open'"),
        ),
        sa.Column("acknowledged_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("acknowledged_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint("window_end >= window_start", name="temporal_window_ordering"),
        sa.CheckConstraint(
            "severity IN ('info','low','medium','high','critical')",
            name="temporal_severity_enum",
        ),
        sa.CheckConstraint(
            "status IN ('open','acknowledged','dismissed','resolved')",
            name="temporal_status_enum",
        ),
    )
    op.create_index(
        "ix_temporal_tenant_engagement",
        "temporal_insights",
        ["tenant_id", "engagement_id", "status", "severity"],
    )
    op.create_index("ix_temporal_kind", "temporal_insights", ["insight_kind"])
    op.create_index(
        "ix_temporal_window",
        "temporal_insights",
        ["window_start", "window_end"],
    )


def downgrade() -> None:
    op.drop_index("ix_temporal_window", table_name="temporal_insights")
    op.drop_index("ix_temporal_kind", table_name="temporal_insights")
    op.drop_index("ix_temporal_tenant_engagement", table_name="temporal_insights")
    op.drop_table("temporal_insights")
