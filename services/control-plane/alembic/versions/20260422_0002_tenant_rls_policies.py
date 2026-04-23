"""Story 1.9 — three-layer tenant isolation: Postgres RLS policies.

Enables Row-Level Security on every canonical-memory table introduced in
migration ``20260422_0001_canonical_memory_schema`` and attaches a
``tenant_rls_<table>`` policy that filters rows by
``app.current_tenant`` — the GUC set by
:func:`deployai_tenancy.session.TenantScopedSession`.

Also creates a ``deployai_app`` role that application code will connect as
starting Story 2.4. Under the superuser connection used today the policies
are still applied because we ``ALTER TABLE ... FORCE ROW LEVEL SECURITY``,
which disables the table-owner bypass.

Tagged ``# expand-contract: expand`` per the NFR74 guardrail (additive — no
column or type alterations on the canonical tables).

Revision ID: 20260422_0002
Revises: 20260422_0001
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260422_0002"
down_revision: str | Sequence[str] | None = "20260422_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CANONICAL_TABLES: tuple[str, ...] = (
    "canonical_memory_events",
    "identity_nodes",
    "identity_attribute_history",
    "identity_supersessions",
    "solidified_learnings",
    "learning_lifecycle_states",
    "tombstones",
    "schema_proposals",
)


def upgrade() -> None:
    """# expand-contract: expand

    Adds RLS + ``tenant_rls_<table>`` policies + ``deployai_app`` role. No
    column or type changes on canonical tables.
    """
    # Role created NOLOGIN by default so an operator can't accidentally leave
    # it logged-in with a null password. Story 2.4 will ALTER ROLE ... LOGIN
    # PASSWORD <secret> at deploy time through the ops runbook; integration
    # tests do the same via an explicit ALTER ROLE fixture.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'deployai_app') THEN
                CREATE ROLE deployai_app NOLOGIN NOINHERIT;
            END IF;
        END
        $$;
        """
    )

    for table in CANONICAL_TABLES:
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


def downgrade() -> None:
    """# expand-contract: contract

    Drops the policies + disables RLS. Keeps the ``deployai_app`` role (roles
    are global and may be shared across future migrations).
    """
    for table in CANONICAL_TABLES:
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON public.{table} FROM deployai_app")
        op.execute(f"DROP POLICY IF EXISTS tenant_rls_{table} ON public.{table}")
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY")
