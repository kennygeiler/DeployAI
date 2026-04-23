"""Canonical memory schema — event log, identity graph, learnings, tombstones.

Story 1.8. Lands the initial ``public``-schema canonical memory substrate
in the DeployAI derivatives cluster:

- ``deployai_uuid_v7()`` — plpgsql UUID v7 generator (Postgres 16 has no
  native ``uuidv7()`` — that ships in Postgres 18). K-sortable IDs per
  the architecture doc's UUID rule.
- ``deployai_forbid_mutation()`` + the
  ``canonical_memory_events_append_only`` trigger — FR1 append-only
  enforcement at the DB layer.
- Tables: ``canonical_memory_events``, ``identity_nodes``,
  ``identity_attribute_history``, ``identity_supersessions``,
  ``solidified_learnings``, ``learning_lifecycle_states``,
  ``tombstones``, ``schema_proposals``.
- Enum type ``learning_state_t``.

Downstream:

- Story 1.9 layers RLS policies (``tenant_rls_<table>``), envelope
  encryption, and ``TenantScopedSession`` on top.
- Story 1.13 populates ``tombstones.tsa_timestamp`` (RFC 3161).
- Story 1.17 owns the ``schema_proposals`` review surface.

Revision ID: 20260422_0001
Revises:
Create Date: 2026-04-23
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "20260422_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ---------------------------------------------------------------------------
# UUID v7 generator — Postgres 16 compatible.
# Layout (16 bytes): 6B unix_ts_ms | 10B random with version=7 + variant=10.
# Requires the `pgcrypto` extension for gen_random_bytes(); installed by
# infra/compose/postgres/init/01-extensions.sql (Story 1.7) and by the
# equivalent RDS parameter-group bootstrap in prod (out of scope here).
# ---------------------------------------------------------------------------
_UUID_V7_FN = r"""
CREATE OR REPLACE FUNCTION deployai_uuid_v7() RETURNS uuid
LANGUAGE plpgsql VOLATILE AS $$
DECLARE
    unix_ts_ms bigint;
    ts_bytes   bytea;
    rand_bytes bytea;
BEGIN
    unix_ts_ms := floor(extract(epoch from clock_timestamp()) * 1000)::bigint;
    ts_bytes   := decode(lpad(to_hex(unix_ts_ms), 12, '0'), 'hex');
    rand_bytes := gen_random_bytes(10);
    -- Version 7 (0111xxxx) in high nibble of byte 6 (offset 0 of rand_bytes).
    rand_bytes := set_byte(rand_bytes, 0, (get_byte(rand_bytes, 0) & 15) | 112);
    -- RFC 4122 variant (10xxxxxx) in high bits of byte 8 (offset 2 of rand_bytes).
    rand_bytes := set_byte(rand_bytes, 2, (get_byte(rand_bytes, 2) & 63) | 128);
    RETURN encode(ts_bytes || rand_bytes, 'hex')::uuid;
END;
$$;
"""


# ---------------------------------------------------------------------------
# Append-only enforcement for canonical_memory_events (FR1).
# ---------------------------------------------------------------------------
_FORBID_MUTATION_FN = r"""
CREATE OR REPLACE FUNCTION deployai_forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'canonical_memory_events is append-only (TG_OP=%)', TG_OP
        USING ERRCODE = 'P0001';
END;
$$;
"""


def upgrade() -> None:
    # expand-contract: expand
    # -----------------------------------------------------------------------
    # 1. Helper functions
    # -----------------------------------------------------------------------
    op.execute(_UUID_V7_FN)
    op.execute(_FORBID_MUTATION_FN)

    # -----------------------------------------------------------------------
    # 2. Enum types
    # -----------------------------------------------------------------------
    op.execute(
        """
        CREATE TYPE learning_state_t AS ENUM (
            'candidate', 'solidified', 'overridden', 'tombstoned'
        );
        """
    )

    # -----------------------------------------------------------------------
    # 3. Tables (in dependency order: identity_nodes before FKs pointing at it)
    # -----------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE canonical_memory_events (
            id            UUID PRIMARY KEY DEFAULT deployai_uuid_v7(),
            tenant_id     UUID NOT NULL,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
            event_type    TEXT NOT NULL,
            graph_epoch   BIGINT NOT NULL DEFAULT 0,
            occurred_at   TIMESTAMPTZ NOT NULL,
            source_ref    TEXT,
            evidence_span JSONB NOT NULL DEFAULT '{}'::jsonb,
            payload       JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX idx_canonical_memory_events_tenant_id_created_at
            ON canonical_memory_events (tenant_id, created_at DESC);
        """
    )

    op.execute(
        """
        CREATE TRIGGER canonical_memory_events_append_only
        BEFORE UPDATE OR DELETE ON canonical_memory_events
        FOR EACH ROW EXECUTE FUNCTION deployai_forbid_mutation();
        """
    )

    op.execute(
        """
        CREATE TABLE identity_nodes (
            id                 UUID PRIMARY KEY DEFAULT deployai_uuid_v7(),
            tenant_id          UUID NOT NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            canonical_name     TEXT NOT NULL,
            primary_email_hash TEXT NOT NULL,
            is_canonical       BOOLEAN NOT NULL DEFAULT true
        );
        CREATE INDEX idx_identity_nodes_tenant_id ON identity_nodes (tenant_id);
        """
    )

    op.execute(
        """
        CREATE TABLE identity_attribute_history (
            id              UUID PRIMARY KEY DEFAULT deployai_uuid_v7(),
            tenant_id       UUID NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            identity_id     UUID NOT NULL REFERENCES identity_nodes(id),
            attribute_name  TEXT NOT NULL,
            attribute_value TEXT NOT NULL,
            valid_from      TIMESTAMPTZ NOT NULL,
            valid_to        TIMESTAMPTZ
        );
        CREATE INDEX idx_identity_attribute_history_identity_valid
            ON identity_attribute_history (identity_id, attribute_name, valid_from DESC);
        -- At most one OPEN (valid_to IS NULL) attribute row per (identity, name).
        CREATE UNIQUE INDEX uq_identity_attribute_history_open
            ON identity_attribute_history (identity_id, attribute_name)
            WHERE valid_to IS NULL;
        """
    )

    op.execute(
        """
        CREATE TABLE identity_supersessions (
            id                     UUID PRIMARY KEY DEFAULT deployai_uuid_v7(),
            tenant_id              UUID NOT NULL,
            created_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
            superseded_identity_id UUID NOT NULL REFERENCES identity_nodes(id),
            canonical_identity_id  UUID NOT NULL REFERENCES identity_nodes(id),
            reason                 TEXT NOT NULL,
            authority_actor_id     UUID,
            CONSTRAINT different_ids CHECK (superseded_identity_id <> canonical_identity_id)
        );
        CREATE INDEX idx_identity_supersessions_tenant_superseded
            ON identity_supersessions (tenant_id, superseded_identity_id);
        """
    )

    op.execute(
        """
        CREATE TABLE solidified_learnings (
            id                  UUID PRIMARY KEY DEFAULT deployai_uuid_v7(),
            tenant_id           UUID NOT NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            belief              TEXT NOT NULL,
            evidence_event_ids  UUID[] NOT NULL,
            application_trigger JSONB NOT NULL DEFAULT '{}'::jsonb,
            state               learning_state_t NOT NULL DEFAULT 'candidate'
        );
        CREATE INDEX idx_solidified_learnings_tenant_id
            ON solidified_learnings (tenant_id);
        """
    )

    op.execute(
        """
        CREATE TABLE learning_lifecycle_states (
            id              UUID PRIMARY KEY DEFAULT deployai_uuid_v7(),
            tenant_id       UUID NOT NULL,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            learning_id     UUID NOT NULL REFERENCES solidified_learnings(id),
            state           learning_state_t NOT NULL,
            transitioned_at TIMESTAMPTZ NOT NULL,
            actor_id        UUID,
            reason          TEXT
        );
        CREATE INDEX idx_learning_lifecycle_states_learning
            ON learning_lifecycle_states (learning_id, transitioned_at DESC);
        """
    )

    op.execute(
        """
        CREATE TABLE tombstones (
            id                 UUID PRIMARY KEY DEFAULT deployai_uuid_v7(),
            tenant_id          UUID NOT NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            original_node_id   UUID NOT NULL,
            retention_reason   TEXT NOT NULL,
            authority_actor_id UUID NOT NULL,
            destroyed_at       TIMESTAMPTZ NOT NULL,
            signature          BYTEA NOT NULL,
            tsa_timestamp      BYTEA
        );
        CREATE INDEX idx_tombstones_tenant_original
            ON tombstones (tenant_id, original_node_id);
        """
    )

    op.execute(
        """
        CREATE TABLE schema_proposals (
            id                 UUID PRIMARY KEY DEFAULT deployai_uuid_v7(),
            tenant_id          UUID NOT NULL,
            created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
            proposer_actor_id  UUID NOT NULL,
            proposed_ddl       TEXT NOT NULL,
            status             TEXT NOT NULL DEFAULT 'pending',
            reviewed_at        TIMESTAMPTZ,
            reviewer_actor_id  UUID
        );
        """
    )


def downgrade() -> None:
    # expand-contract: contract
    # Reverse dependency order. Triggers fall with their parent table.
    op.execute("DROP TABLE IF EXISTS schema_proposals;")
    op.execute("DROP TABLE IF EXISTS tombstones;")
    op.execute("DROP TABLE IF EXISTS learning_lifecycle_states;")
    op.execute("DROP TABLE IF EXISTS solidified_learnings;")
    op.execute("DROP TABLE IF EXISTS identity_supersessions;")
    op.execute("DROP TABLE IF EXISTS identity_attribute_history;")
    op.execute("DROP TABLE IF EXISTS identity_nodes;")
    op.execute("DROP TABLE IF EXISTS canonical_memory_events;")
    op.execute("DROP TYPE  IF EXISTS learning_state_t;")
    op.execute("DROP FUNCTION IF EXISTS deployai_forbid_mutation();")
    op.execute("DROP FUNCTION IF EXISTS deployai_uuid_v7();")
