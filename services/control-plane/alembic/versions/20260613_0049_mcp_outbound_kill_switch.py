"""v2 Phase 5 Wave 2F — per-tenant outbound MCP kill switch.

# expand-contract: expand — adds one nullable-with-default column to
# ``app_tenants``; old rows backfill to ``false`` on the server-default,
# no downtime, no application change required to deploy in either order.

Threat-model §5.5 Option B: the kill switch is a **single top-level
boolean on ``app_tenants``**, not a per-MCP-config flag on
``tenant_mcp_configs``.

Rationale recap (so the column placement survives a future reviewer):

  - The kill switch is an *incident-response* primitive. When the
    tenant-admin (or DeployAI on-call) flips it, the intent is "stop
    Kenny from making **any** external call for this tenant right now",
    not "disable the Slack integration but leave Linear up". Putting the
    flag on ``app_tenants`` is one row to flip and one row to read on
    every outbound call's hot path.
  - ``tenant_mcp_configs.enabled`` already serves the per-integration
    on/off use case (e.g. "we don't use Notion anymore"). Overloading it
    for incident response would conflate steady-state configuration with
    a security primitive — and would require an N-row UPDATE under
    pressure, which is the worst time to discover the partial-write
    failure mode.
  - The 5-second staleness in :class:`DbMcpKillSwitch`'s in-memory cache
    is acceptable because §5.5 explicitly says "order-of-seconds is
    fine for v1"; the threat model trades eager invalidation for
    avoiding a Redis round-trip on every tool call.

The partial index on ``mcp_outbound_disabled = true`` is included
because in normal operation 0 rows match it (cheap to maintain) and
because it makes the future admin query "which tenants are killed right
now" an index-only scan rather than a seq-scan over every tenant row.
Reviewer may drop it post-merge if it's deemed not worth the catalog
bookkeeping — the application-layer cache means the production hot
path never reads through it.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260613_0049"
down_revision: str | None = "20260613_0048"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


COLUMN_NAME = "mcp_outbound_disabled"
PARTIAL_INDEX_NAME = "idx_app_tenants_mcp_outbound_disabled_true"


def upgrade() -> None:
    # 0042 sets the database-level search_path to ag_catalog,"$user",public.
    # Pin this migration's DDL to public so the ALTER TABLE lands against
    # the public.app_tenants every other migration touches.
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.add_column(
        "app_tenants",
        sa.Column(
            COLUMN_NAME,
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    # Partial index — 0 rows in steady state, costs ~16KB of catalog
    # bookkeeping. Makes "list every killed tenant" an index-only scan
    # for the future admin dashboard (Wave 3H). The application hot path
    # reads through the 5s in-memory cache in ``DbMcpKillSwitch``, so
    # this index never participates in the per-call lookup.
    op.create_index(
        PARTIAL_INDEX_NAME,
        "app_tenants",
        [COLUMN_NAME],
        postgresql_where=sa.text(f"{COLUMN_NAME} = true"),
    )


def downgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.drop_index(PARTIAL_INDEX_NAME, table_name="app_tenants")
    op.drop_column("app_tenants", COLUMN_NAME)
