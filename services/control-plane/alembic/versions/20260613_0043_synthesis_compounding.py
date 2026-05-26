"""v2 Phase 0.5 — compounding synthesis layer (matrix_insights extensions + jobs).

# expand-contract: expand — additive columns + check constraint + one new
# table. Existing rows survive because the new columns are NOT NULL with
# server defaults that backfill in place.

Extends ``matrix_insights`` so Kenny + Oracle syntheses can be refreshed
in-place and tracked as stale when their causal sources change:

- ``last_refreshed_at`` (timestamptz, default now())
- ``stale`` (bool, default false)
- CHECK that ``citation_event_ids`` is non-empty when ``agent`` is
  ``oracle`` or ``kenny`` (per scope-v2 §3.1)
- agent CHECK widened to include ``'kenny'``

Adds the ``synthesis_refresh_jobs`` queue table. Jobs are enqueued by the
ledger emitter hook (see ``control_plane/ledger/emitter.py``) when a
``proposal_accepted`` / ``insight_opened`` / ``member_added`` event lands,
and drained by ``POST /internal/v1/admin/synthesis/drain`` (Phase 0.6
will replace the manual drain with a cron worker).
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0043"
down_revision: str | None = "20260613_0042"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 0042 sets the database-level search_path to ag_catalog,"$user",public
    # for new connections so AGE Cypher calls work without per-statement
    # configuration. We pin this migration's DDL to the public schema so the
    # new objects land where every other DeployAI table lives.
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.add_column(
        "matrix_insights",
        sa.Column(
            "last_refreshed_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
    )
    op.add_column(
        "matrix_insights",
        sa.Column(
            "stale",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Widen the agent enum: existing rows are 'oracle' or 'master_strategist';
    # we keep both and add 'kenny' for the LLM synthesis worker output.
    op.drop_constraint("ck_matrix_insights_agent", "matrix_insights", type_="check")
    op.create_check_constraint(
        "ck_matrix_insights_agent",
        "matrix_insights",
        "agent IN ('oracle', 'master_strategist', 'kenny')",
    )

    # Per scope-v2 §3.1: kenny synthesis rows MUST cite at least one source
    # event. Existing 'oracle' insights are produced by deterministic
    # predicates that cite nodes/edges (not events), so this constraint is
    # narrowed to 'kenny' to avoid breaking the predicate-driven flow. Phase
    # 0.6 lint adds an out-of-band check for oracle rows where event cites
    # are expected.
    op.create_check_constraint(
        "ck_matrix_insights_source_events_present",
        "matrix_insights",
        "agent <> 'kenny' OR cardinality(citation_event_ids) > 0",
    )

    op.create_index(
        "idx_matrix_insights_stale_refreshed",
        "matrix_insights",
        ["tenant_id", "stale", "last_refreshed_at"],
    )

    op.create_table(
        "synthesis_refresh_jobs",
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
            sa.ForeignKey("engagements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.Text(), nullable=False),
        sa.Column("target_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "trigger_event_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "attempts",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "enqueued_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('decision_provenance', 'risk_explainer', 'stakeholder_brief')",
            name="ck_synthesis_refresh_jobs_kind",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'done', 'failed')",
            name="ck_synthesis_refresh_jobs_status",
        ),
    )
    op.create_index(
        "idx_synthesis_refresh_jobs_pending",
        "synthesis_refresh_jobs",
        ["tenant_id", "engagement_id", "status", "enqueued_at"],
    )
    op.create_index(
        "idx_synthesis_refresh_jobs_target",
        "synthesis_refresh_jobs",
        ["target_id", "kind"],
    )


def downgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")
    # drop_table cascades index drops, so we don't drop the synthesis indexes
    # separately — DROP INDEX after DROP TABLE would error with UndefinedObject.
    op.drop_table("synthesis_refresh_jobs")

    op.drop_index("idx_matrix_insights_stale_refreshed", table_name="matrix_insights")
    op.drop_constraint(
        "ck_matrix_insights_source_events_present",
        "matrix_insights",
        type_="check",
    )
    op.drop_constraint("ck_matrix_insights_agent", "matrix_insights", type_="check")
    op.create_check_constraint(
        "ck_matrix_insights_agent",
        "matrix_insights",
        "agent IN ('oracle', 'master_strategist')",
    )

    op.drop_column("matrix_insights", "stale")
    op.drop_column("matrix_insights", "last_refreshed_at")
