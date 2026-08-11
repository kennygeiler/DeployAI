"""Pilot-refresh A3a — denormalized tenant_id on the ledger edge tables.

# expand-contract: expand — adds one nullable ``tenant_id`` column per edge
# table, backfills it from the parent ``ledger_events`` row, and installs a
# BEFORE INSERT trigger that fills it for writers that predate the column.
# No existing column or type changes; NOT NULL is deferred to a later
# contract migration once every writer is proven to populate it.

``ledger_event_causes`` and ``ledger_event_affects`` were created (0035/0036)
without a tenant column — isolation was "enforced by the parent ledger_events
row". That made them the only ledger tables migration 0053 could not attach a
direct RLS policy to. A denormalized ``tenant_id`` (cheap: both tables are
pure junction tables keyed by ``event_id``) lets 0053 apply the exact same
``tenant_rls_<table>`` policy shape as everywhere else.

The trigger keeps every existing writer working unmodified (ORM emitter, the
ledger-backfill CLI's raw INSERTs, scenario builders): when an INSERT omits
``tenant_id`` (or passes NULL), the trigger copies it from the referenced
``ledger_events`` row. Under an RLS-subject role the parent lookup is itself
policy-filtered, so a cross-tenant ``event_id`` yields NULL and the WITH CHECK
policy rejects the row — exactly the failure we want.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260811_0051"
down_revision: str | None = "20260613_0050"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


EDGE_TABLES: tuple[str, ...] = ("ledger_event_causes", "ledger_event_affects")


def upgrade() -> None:
    for table in EDGE_TABLES:
        op.add_column(
            table,
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("app_tenants.id", ondelete="CASCADE"),
                nullable=True,
            ),
        )
        # Backfill from the parent event. Both tables are small junction
        # tables; a single UPDATE ... FROM is fine at pilot scale.
        op.execute(
            f"""
            UPDATE public.{table} AS edge
            SET tenant_id = ev.tenant_id
            FROM public.ledger_events AS ev
            WHERE edge.event_id = ev.id
              AND edge.tenant_id IS NULL
            """
        )
        op.create_index(f"ix_{table}_tenant", table, ["tenant_id"])

    # One shared trigger function; TG_TABLE_NAME is irrelevant because both
    # tables carry the same (event_id, tenant_id) shape.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION deployai_ledger_edge_fill_tenant()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            IF NEW.tenant_id IS NULL THEN
                SELECT tenant_id INTO NEW.tenant_id
                FROM public.ledger_events
                WHERE id = NEW.event_id;
            END IF;
            RETURN NEW;
        END;
        $$;
        """
    )
    for table in EDGE_TABLES:
        op.execute(
            f"""
            CREATE TRIGGER trg_{table}_fill_tenant
            BEFORE INSERT ON public.{table}
            FOR EACH ROW EXECUTE FUNCTION deployai_ledger_edge_fill_tenant();
            """
        )


def downgrade() -> None:
    for table in EDGE_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_fill_tenant ON public.{table}")
    op.execute("DROP FUNCTION IF EXISTS deployai_ledger_edge_fill_tenant()")
    for table in EDGE_TABLES:
        op.drop_index(f"ix_{table}_tenant", table_name=table)
        op.drop_column(table, "tenant_id")
