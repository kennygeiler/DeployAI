"""v2 Phase 5 Wave 1A — tenant_mcp_configs table for MCP outbound integrations.

# expand-contract: expand — new isolated table + indexes + RLS policy, no
# changes to existing rows or columns.

One row per (tenant, named MCP integration) — the tenant-admin curated
catalog of external MCP servers Agent Kenny is allowed to call (Slack,
Linear, GDrive, Notion, GitHub for v1). At the start of every Kenny v2
turn the agent loop loads ``WHERE tenant_id = :t AND enabled = true``,
fetches each MCP server's advertised tool list, and merges the
intersection of ``allowed_tools`` (when non-null) into the tool
registry namespaced by ``connector_kind`` (e.g. ``slack.search_messages``).

The ``encrypted_auth_token`` column is BYTEA because Wave 2D will wire
the existing ``deployai_tenancy.envelope.encrypt_field`` round-trip
(pgcrypto ``pgp_sym_encrypt_bytea`` under the tenant DEK) — this Wave 1A
ships the column shape so the route + client work in Wave 2 can write
to it without a follow-up migration. See scope-v2 §9.1 + §9.4.

Postgres RLS is enabled here so that the ``deployai_app`` low-privilege
role (Story 1.9) cannot read another tenant's MCP rows even when the
application layer forgets to filter. Mirrors the
``tenant_rls_canonical_memory_events`` shape from migration
``20260422_0002_tenant_rls_policies.py``.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260613_0048"
down_revision: str | None = "20260613_0047"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


TABLE_NAME = "tenant_mcp_configs"

# v1 connector catalog — every row's ``connector_kind`` must be one of
# these. Adding a new connector is a single-line migration that widens
# the CHECK; the application-layer client registry must also grow a
# branch, so the constraint forces a coordinated change.
CONNECTOR_KINDS: tuple[str, ...] = (
    "slack",
    "linear",
    "gdrive",
    "notion",
    "github",
)

# v1 transport catalog — ``http_sse`` is the only MCP transport Wave 2's
# client speaks. ``stdio`` and ``websocket`` are documented in the MCP
# spec; we leave room in the column shape but constrain to what's
# actually wired.
TRANSPORTS: tuple[str, ...] = ("http_sse",)


def upgrade() -> None:
    # 0042 sets the database-level search_path to ag_catalog,"$user",public.
    # Pin this migration's DDL to public so the new table lands where every
    # other DeployAI table lives.
    op.execute("SET LOCAL search_path = public, ag_catalog")

    op.create_table(
        TABLE_NAME,
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
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("connector_kind", sa.Text(), nullable=False),
        sa.Column(
            "transport",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'http_sse'"),
        ),
        sa.Column("endpoint", sa.Text(), nullable=False),
        # TODO Wave 2D: write path will call
        # ``deployai_tenancy.envelope.encrypt_field`` under the
        # tenant-scoped session so the bytes here are pgcrypto
        # ``pgp_sym_encrypt_bytea`` ciphertext rather than raw token
        # material. Wave 1A only ships the column shape.
        sa.Column("encrypted_auth_token", postgresql.BYTEA(), nullable=True),
        # Null means "every tool the MCP server advertises is allowed"
        # (tenant-admin opted in to the whole connector). Non-null is a
        # strict allow-list of MCP tool names; the agent loop must drop
        # any tool not in this list before exposing it to the LLM.
        sa.Column(
            "allowed_tools",
            postgresql.ARRAY(sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "connector_kind IN (" + ", ".join(f"'{k}'" for k in CONNECTOR_KINDS) + ")",
            name="ck_tenant_mcp_configs_connector_kind",
        ),
        sa.CheckConstraint(
            "transport IN (" + ", ".join(f"'{t}'" for t in TRANSPORTS) + ")",
            name="ck_tenant_mcp_configs_transport",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "name",
            name="uq_tenant_mcp_configs_tenant_id_name",
        ),
    )

    # Hot-path lookup at agent loop start: "give me every enabled MCP
    # config for this tenant". Tenant + enabled covers the common case;
    # the planner can use it as an index-only scan when enabled = true.
    op.create_index(
        "idx_tenant_mcp_configs_tenant_id_enabled",
        TABLE_NAME,
        ["tenant_id", "enabled"],
    )

    # RLS — mirrors the canonical_memory shape from migration 0002. The
    # ``deployai_app`` role connects without BYPASSRLS, so a forgotten
    # tenant filter at the application layer still fails closed.
    op.execute(f"ALTER TABLE public.{TABLE_NAME} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{TABLE_NAME} FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS tenant_rls_{TABLE_NAME} ON public.{TABLE_NAME}")
    op.execute(
        f"""
        CREATE POLICY tenant_rls_{TABLE_NAME}
            ON public.{TABLE_NAME}
            USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
            WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
        """
    )
    op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{TABLE_NAME} TO deployai_app")


def downgrade() -> None:
    op.execute("SET LOCAL search_path = public, ag_catalog")
    op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON public.{TABLE_NAME} FROM deployai_app")
    op.execute(f"DROP POLICY IF EXISTS tenant_rls_{TABLE_NAME} ON public.{TABLE_NAME}")
    op.execute(f"ALTER TABLE public.{TABLE_NAME} NO FORCE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{TABLE_NAME} DISABLE ROW LEVEL SECURITY")
    # drop_table cascades the index drop.
    op.drop_table(TABLE_NAME)
