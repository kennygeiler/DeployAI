# Canonical memory — schema contract

> Landed in **Story 1.8**. Extended by **Story 1.9** (RLS +
> envelope-encryption primitives + `TenantScopedSession`), Story 1.10
> (cross-tenant fuzz), Story 1.13 (RFC 3161 `tsa_timestamp`), and Story
> 1.17 (`schema_proposals` review surface).

The canonical memory substrate is the immutable record of everything an
account's Deployment Strategist has observed: events, people, learnings,
and tombstones. It lives in the **DeployAI derivatives** Postgres
cluster (NFR25 logical R.O.T. bifurcation V1), under the `public`
schema. Seed fixtures for the local dev stack live in a separate
`fixtures` schema (authored by Story 1.7) so the canonical memory
migration lands cleanly on a freshly booted stack.

---

## Tables

| Table | Purpose | FR / NFR hooks |
|---|---|---|
| `canonical_memory_events` | Immutable append-only event log | FR1 |
| `identity_nodes` | One canonical person per tenant | FR2, DP11 |
| `identity_attribute_history` | Time-versioned role/title/email per identity | FR2, DP11 |
| `identity_supersessions` | Duplicate-identity resolution link | FR3 |
| `solidified_learnings` | Belief + evidence + application trigger + lifecycle state | FR4 |
| `learning_lifecycle_states` | Append-only state-transition log for learnings | FR4, NFR74 |
| `tombstones` | Retention-driven destruction record (signed) | FR5, NFR33, NFR38 |
| `schema_proposals` | Staging area for schema-evolution proposals | Forward-reserved for Story 1.17 |

Every row in every table carries:

- `id UUID PK DEFAULT deployai_uuid_v7()`
- `tenant_id UUID NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

## Append-only contract

`canonical_memory_events` is the only table of the substrate that is
literally append-only at the database layer. A row-level trigger,
`canonical_memory_events_append_only`, invokes
`deployai_forbid_mutation()` on every `BEFORE UPDATE OR DELETE`:

```text
ERROR:  canonical_memory_events is append-only (TG_OP=UPDATE)
SQLSTATE: P0001
```

Application code MUST NOT attempt `UPDATE` or `DELETE` on this table.
Semantic "edits" are modelled by appending a newer event with a
relationship back to the original (e.g. an `override_event` appended per
Story 10). Semantic "deletions" use `tombstones` (see §Tombstones).

Other canonical-memory tables (`identity_nodes`,
`identity_attribute_history`, `solidified_learnings`, etc.) support
`UPDATE` because their own schemas model change as a first-class event
(attribute history's `valid_to`, learning's `learning_lifecycle_states`
log). Don't add the trigger to those tables without rethinking the
append-only narrative.

## UUID v7 — `deployai_uuid_v7()`

All entity IDs use UUID v7 (K-sortable, time-ordered) per the
architecture doc's UUID rule. Postgres 16 has no native `uuidv7()`
(that ships in Postgres 18), so Story 1.8's migration creates a
plpgsql implementation:

- High 48 bits: `unix_ts_ms` (milliseconds since epoch)
- Bits 48–51: version marker (`0111` = v7)
- Bits 52–63: random (from `pgcrypto.gen_random_bytes`)
- Bits 64–65: RFC 4122 variant (`10`)
- Bits 66–127: random

Monotonicity within the same millisecond bucket is **not** guaranteed —
that's acceptable for the K-sortable property we care about (index
locality, time-ordered scans). When you need strict monotonicity,
order by `created_at` or by a dedicated sequence column.

## Expand-contract migrations — the `# expand-contract:` marker

NFR74 requires schema migrations follow the expand-contract pattern,
with canonical-memory migrations additive wherever possible. The
`test_migration_guardrails.py` unit test scans every file in
`alembic/versions/` and fails when a migration:

1. references any canonical-memory table name, **AND**
2. contains `ALTER COLUMN` (via `op.alter_column` or raw SQL), **AND**
3. omits a marker comment `# expand-contract: expand` or
   `# expand-contract: contract` inside the `upgrade()` body.

Authors follow the pattern:

```python
def upgrade() -> None:
    # expand-contract: expand
    op.alter_column(...)  # e.g. add a new nullable column or widen a type
```

A matching `contract` migration lands in a follow-up PR after all
readers are updated — at least one release later (NFR74).

The guardrail is intentionally marker-based rather than diff-based: the
marker forces an author to declare intent, which is the review-hook a
schema-evolution policy needs. The guardrail doesn't verify that the
contract PR actually lands — that's governance, not automation.

## Tombstones

A tombstone is the canonical record of a destroyed node. Its fields:

- `original_node_id` — the destroyed row's id. No foreign key: the
  referenced row is usually already gone.
- `retention_reason` — free-text justification tying to NFR33 retention
  classes or a legal-hold release.
- `authority_actor_id` — the `platform_admin` or `customer_records_officer`
  who authorized destruction.
- `destroyed_at` — wall-clock time of destruction.
- `signature` — Ed25519 signature over the tombstone payload (key
  custody lands with the per-device hardware-backed signing work under
  Story 11.2; key handoff for control-plane-signed tombstones is
  tracked as a deferred control).
- `tsa_timestamp` — RFC 3161 TSR. **Nullable** until Story 1.13 wires
  the FreeTSA + AWS fallback into the signing pipeline.

## Tenant isolation (Story 1.9)

RLS policies `tenant_rls_<table>` are applied to every canonical-memory
table by migration `20260422_0002_tenant_rls_policies.py` (expand).
`FORCE ROW LEVEL SECURITY` is enabled so the table owner is not
exempted. Every application query must pass through
`deployai_tenancy.TenantScopedSession`, which issues
`SELECT set_config('app.current_tenant', :tid, true)` inside the
transaction that the policy reads via
`current_setting('app.current_tenant', true)::uuid`. A `deployai_app`
role is created as the application connection user (default swap in
Story 2.4).

The `@requires_tenant_scope` decorator in
`deployai_tenancy.decorators` is the application-layer guard; it raises
`MissingTenantScope` before any SQL leaves the process when a function
is handed a raw unscoped session.

Envelope-encryption helpers (`encrypt_field` / `decrypt_field`) wrap
`pgcrypto`'s `pgp_sym_encrypt_bytea` / `pgp_sym_decrypt_bytea` and
require a `TenantScopedSession`. The dev-mode `InMemoryDEKProvider`
ships now; the AWS-KMS-backed provider lands in Story 3.x.

See [`docs/security/tenant-isolation.md`](security/tenant-isolation.md)
for the full three-layer rationale.

## Related files

- Migrations:
  - `services/control-plane/alembic/versions/20260422_0001_canonical_memory_schema.py` (schema)
  - `services/control-plane/alembic/versions/20260422_0002_tenant_rls_policies.py` (RLS, Story 1.9)
- ORM models: `services/control-plane/src/control_plane/domain/canonical_memory/`
- Tenancy package: `services/_shared/tenancy/` (Story 1.9)
- Migration guardrail: `services/control-plane/tests/unit/test_migration_guardrails.py`
- Integration tests: `services/control-plane/tests/integration/test_canonical_memory_schema.py`, `test_tenant_isolation.py`
- CI workflow: `.github/workflows/schema.yml`
