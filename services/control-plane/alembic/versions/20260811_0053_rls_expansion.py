"""Pilot-refresh A3a — expand Row-Level Security to every tenant_id-bearing table.

Story 1.9 (migration ``20260422_0002``) enabled RLS on the 8 canonical-memory
tables and ``20260613_0048`` covered ``tenant_mcp_configs`` — but the ~40
tenant-scoped tables added since then shipped with **no** database-layer
isolation: a session without the ``app.current_tenant`` GUC (or with a spoofed
tenant argument, under an RLS-subject role) could read every tenant's ledger,
matrix, engagements, and chat history. This migration attaches the exact
policy shape from 0002 to every remaining table that carries a ``tenant_id``
column, with FORCE ROW LEVEL SECURITY and CRUD grants for ``deployai_app``.

Deliberately not covered (and why):

- ``app_tenants`` — the tenant registry itself; global by definition (auth
  and provisioning must enumerate/resolve tenants before any scope exists).
  ``deployai_app`` gets SELECT so scoped sessions can resolve tenant rows.
- ``internal_service_tokens`` — auth-infra table (migration 0052); token
  lookup happens before a tenant scope exists.
- ``webhook_deliveries`` — carries no ``tenant_id`` (child of
  ``tenant_webhooks`` via ``webhook_id``); needs a denormalized column +
  backfill like 0051 did for the ledger edge tables. Follow-up.

Tagged ``# expand-contract: expand`` per the NFR74 guardrail (additive — no
column or type alterations).

Revision ID: 20260811_0053
Revises: 20260811_0052
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260811_0053"
down_revision: str | None = "20260811_0052"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Every tenant_id-bearing table not already covered by 0002 / 0048.
# ``ledger_event_causes`` / ``ledger_event_affects`` gained their denormalized
# tenant_id in 0051 specifically so they could join this list.
TENANT_TABLES: tuple[str, ...] = (
    "adjudication_queue_items",
    "agent_audit_traces",
    "app_users",
    "break_glass_sessions",
    "edge_agents",
    "email_ingest_events",
    "embedding_jobs",
    "engagement_members",
    "engagements",
    "ingestion_runs",
    "integrations",
    "ledger_event_affects",
    "ledger_event_causes",
    "ledger_events",
    "lint_flags",
    "matrix_edges",
    "matrix_insights",
    "matrix_nodes",
    "matrix_proposals",
    "matrix_snapshots",
    "meeting_webhook_events",
    "oracle_chat_turns",
    "oracle_conversations",
    "phase_transition_proposals",
    "private_override_annotations",
    "solidification_review_queue",
    "strategist_action_queue_items",
    "strategist_activity_events",
    "strategist_solidification_queue_items",
    "strategist_validation_queue_items",
    "synthesis_refresh_jobs",
    "temporal_insights",
    "tenant_agent_prompts",
    "tenant_api_keys",
    "tenant_deployment_phases",
    "tenant_llm_configs",
    "tenant_llm_daily_budget",
    "tenant_member_roles",
    "tenant_node_types",
    "tenant_webhooks",
)


def upgrade() -> None:
    """# expand-contract: expand

    Adds RLS + ``tenant_rls_<table>`` policies + grants. No column or type
    changes on any table.
    """
    # 0042 sets the database-level search_path to ag_catalog,"$user",public;
    # pin DDL to public like the surrounding migrations do.
    op.execute("SET LOCAL search_path = public, ag_catalog")

    for table in TENANT_TABLES:
        op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
        # DROP-before-CREATE keeps the migration idempotent after a partial
        # failure. The policy shape is identical on every run; we don't need
        # an IF NOT EXISTS guard, just a clean reset.
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

    # Auth-infra tables the app role must read outside any tenant scope:
    # tenant resolution (`_require_tenant`) and service-token verification.
    op.execute("GRANT SELECT ON public.app_tenants TO deployai_app")
    op.execute("GRANT SELECT ON public.internal_service_tokens TO deployai_app")


def downgrade() -> None:
    """# expand-contract: contract

    Drops the policies + disables RLS. Keeps the ``deployai_app`` role (roles
    are global; created by 0002).
    """
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.execute("REVOKE SELECT ON public.internal_service_tokens FROM deployai_app")
    op.execute("REVOKE SELECT ON public.app_tenants FROM deployai_app")
    for table in TENANT_TABLES:
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON public.{table} FROM deployai_app")
        op.execute(f"DROP POLICY IF EXISTS tenant_rls_{table} ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
