#!/usr/bin/env bash
#
# Story 1.7 — idempotent seeder for the local dev stack.
#
# Populates the `fixtures` schema with one synthetic tenant, ≥5 stakeholders,
# ≥20 canonical events, and a sample phase row. Safe to re-run.
#
# Usage:
#   ./infra/compose/seed/seed.sh
#
# Requires:
#   - The `postgres` compose service running + healthy.
#   - `docker compose` available on PATH.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
COMPOSE_FILE="${REPO_ROOT}/infra/compose/docker-compose.yml"
ENV_FILE="${REPO_ROOT}/infra/compose/.env"

if [[ ! -f "${ENV_FILE}" ]]; then
    echo "seed: ${ENV_FILE} not found; run 'make dev' first" >&2
    exit 1
fi

# shellcheck disable=SC1090
source "${ENV_FILE}"
: "${POSTGRES_DB:=deployai}"
: "${POSTGRES_USER:=deployai}"

DC=(docker compose --env-file "${ENV_FILE}" -f "${COMPOSE_FILE}")

echo "seed: applying schema.sql"
"${DC[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" < "${SCRIPT_DIR}/schema.sql"

echo "seed: inserting synthetic tenant + fixtures"
"${DC[@]}" exec -T postgres psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" <<'SQL'
BEGIN;

TRUNCATE fixtures.phase_states, fixtures.canonical_events, fixtures.identity_nodes, fixtures.tenants RESTART IDENTITY CASCADE;

WITH tenant AS (
    INSERT INTO fixtures.tenants (tenant_id, name)
    VALUES ('00000000-0000-7000-8000-000000000001'::uuid, 'acme-pilot')
    RETURNING tenant_id
)
INSERT INTO fixtures.identity_nodes (identity_id, tenant_id, display_name, role, email)
SELECT gen_random_uuid(), tenant_id, display_name, role, email
FROM tenant,
     (VALUES
        ('Dana Carter',     'chief-of-staff',        'dana@acme.test'),
        ('Priya Raman',     'deputy-director',       'priya@acme.test'),
        ('Marcus Okafor',   'policy-lead',           'marcus@acme.test'),
        ('Yuki Tanaka',     'counsel',               'yuki@acme.test'),
        ('Sam Lindgren',    'budget-analyst',        'sam@acme.test'),
        ('Rita Alvarez',    'communications-lead',   'rita@acme.test')
     ) AS v(display_name, role, email);

-- ≥ 20 canonical events across the synthetic tenant.
WITH tenant AS (SELECT tenant_id FROM fixtures.tenants WHERE name = 'acme-pilot')
INSERT INTO fixtures.canonical_events (event_id, tenant_id, event_type, payload, occurred_at)
SELECT
    gen_random_uuid(),
    tenant.tenant_id,
    event_type,
    jsonb_build_object('seq', seq, 'note', 'fixture-event'),
    now() - (seq || ' hours')::interval
FROM tenant,
     generate_series(1, 24) AS seq,
     LATERAL (
        SELECT (ARRAY['meeting.scheduled','meeting.held','email.received',
                      'decision.recorded','action.assigned','action.completed',
                      'memo.drafted','phase.transitioned'])[1 + (seq % 8)] AS event_type
     ) et;

-- Sample phase row.
WITH tenant AS (SELECT tenant_id FROM fixtures.tenants WHERE name = 'acme-pilot')
INSERT INTO fixtures.phase_states (phase_row_id, tenant_id, phase_id, phase_state)
SELECT gen_random_uuid(), tenant_id, 'discovery', 'active' FROM tenant;

COMMIT;

-- Sanity summary
SELECT 'tenants'        AS table_name, COUNT(*) AS rows FROM fixtures.tenants
UNION ALL SELECT 'identity_nodes', COUNT(*) FROM fixtures.identity_nodes
UNION ALL SELECT 'canonical_events', COUNT(*) FROM fixtures.canonical_events
UNION ALL SELECT 'phase_states',  COUNT(*) FROM fixtures.phase_states;
SQL

echo "seed: done"
