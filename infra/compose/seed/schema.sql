-- Story 1.7 — seed fixtures schema.
--
-- Kept intentionally separate from `public` so Story 1.8's canonical
-- memory migrations (canonical_memory_events, identity_nodes, etc.)
-- land cleanly without colliding with pre-existing fixture data.
-- Story 1.8 may choose to drop this schema once real seeded journeys exist.

CREATE SCHEMA IF NOT EXISTS fixtures;

CREATE TABLE IF NOT EXISTS fixtures.tenants (
    tenant_id    UUID PRIMARY KEY,
    name         TEXT NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fixtures.identity_nodes (
    identity_id   UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL REFERENCES fixtures.tenants(tenant_id) ON DELETE CASCADE,
    display_name  TEXT NOT NULL,
    role          TEXT NOT NULL,
    email         TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fixtures.canonical_events (
    event_id     UUID PRIMARY KEY,
    tenant_id    UUID NOT NULL REFERENCES fixtures.tenants(tenant_id) ON DELETE CASCADE,
    event_type   TEXT NOT NULL,
    payload      JSONB NOT NULL DEFAULT '{}'::jsonb,
    occurred_at  TIMESTAMPTZ NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS fixtures.phase_states (
    phase_row_id  UUID PRIMARY KEY,
    tenant_id     UUID NOT NULL REFERENCES fixtures.tenants(tenant_id) ON DELETE CASCADE,
    phase_id      TEXT NOT NULL,
    phase_state   TEXT NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_canonical_events_tenant ON fixtures.canonical_events(tenant_id);
CREATE INDEX IF NOT EXISTS idx_identity_nodes_tenant  ON fixtures.identity_nodes(tenant_id);
