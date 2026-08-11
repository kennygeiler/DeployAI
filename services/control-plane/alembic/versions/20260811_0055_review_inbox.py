"""Pilot-refresh E1/E4 — review_items table + proposal auto-accept settings.

Creates the unified Review Inbox queue table (``review_items``, tickets
E1-E3: agent escalations, citation disputes, and the commitment-confirmation
schema slot for Wave 3) with FORCE ROW LEVEL SECURITY and the standard
``tenant_rls_<table>`` policy shape from migration 0053 — the RLS catalog
test (``tests/integration/test_rls_expansion.py``) discovers every
tenant_id-bearing table and fails if one ships without a policy.

Also adds the E4 confidence-threshold settings to ``tenant_llm_configs``
(the existing per-tenant settings row the Settings UI already edits):

- ``proposal_auto_accept_threshold`` — 0..1, NULL = auto-accept off.
- ``sampling_audit_rate`` — 0..1 fraction of would-be auto-accepted
  proposals held back for human spot-check (deterministic by proposal id).

Tagged ``# expand-contract: expand`` per the NFR74 guardrail (additive).

Revision ID: 20260811_0055
Revises: 20260811_0054
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260811_0055"
down_revision: str | None = "20260811_0054"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """# expand-contract: expand"""
    # 0042 sets the database-level search_path to ag_catalog,"$user",public;
    # pin DDL to public like the surrounding migrations do.
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.create_table(
        "review_items",
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
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default=sa.text("'open'")),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column("created_by", sa.String(length=200), nullable=True),
        sa.Column("resolved_by", sa.String(length=200), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind IN ('agent_escalation','citation_dispute','commitment_confirmation')",
            name="ck_review_items_kind",
        ),
        sa.CheckConstraint(
            "status IN ('open','resolved','dismissed')",
            name="ck_review_items_status",
        ),
    )
    op.create_index("ix_review_items_tenant_status", "review_items", ["tenant_id", "status"])
    op.create_index(
        "ix_review_items_tenant_kind_status",
        "review_items",
        ["tenant_id", "kind", "status"],
    )
    op.create_index("ix_review_items_engagement", "review_items", ["engagement_id"])

    # RLS — exact policy shape from migration 0053 so the catalog test's
    # discovery invariant holds for the new table.
    op.execute("ALTER TABLE public.review_items ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.review_items FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS tenant_rls_review_items ON public.review_items")
    op.execute(
        """
        CREATE POLICY tenant_rls_review_items
            ON public.review_items
            USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        """
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON public.review_items TO deployai_app")

    # E4 — per-tenant auto-accept settings on the existing settings row.
    op.add_column(
        "tenant_llm_configs",
        sa.Column("proposal_auto_accept_threshold", sa.Double(), nullable=True),
    )
    op.add_column(
        "tenant_llm_configs",
        sa.Column("sampling_audit_rate", sa.Double(), nullable=False, server_default=sa.text("0")),
    )
    op.create_check_constraint(
        "ck_tenant_llm_configs_auto_accept_threshold",
        "tenant_llm_configs",
        "proposal_auto_accept_threshold IS NULL "
        "OR (proposal_auto_accept_threshold >= 0 AND proposal_auto_accept_threshold <= 1)",
    )
    op.create_check_constraint(
        "ck_tenant_llm_configs_sampling_audit_rate",
        "tenant_llm_configs",
        "sampling_audit_rate >= 0 AND sampling_audit_rate <= 1",
    )


def downgrade() -> None:
    """# expand-contract: contract"""
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.drop_constraint(
        "ck_tenant_llm_configs_sampling_audit_rate",
        "tenant_llm_configs",
        type_="check",
    )
    op.drop_constraint(
        "ck_tenant_llm_configs_auto_accept_threshold",
        "tenant_llm_configs",
        type_="check",
    )
    op.drop_column("tenant_llm_configs", "sampling_audit_rate")
    op.drop_column("tenant_llm_configs", "proposal_auto_accept_threshold")

    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON public.review_items FROM deployai_app")
    op.execute("DROP POLICY IF EXISTS tenant_rls_review_items ON public.review_items")
    op.drop_index("ix_review_items_engagement", table_name="review_items")
    op.drop_index("ix_review_items_tenant_kind_status", table_name="review_items")
    op.drop_index("ix_review_items_tenant_status", table_name="review_items")
    op.drop_table("review_items")
