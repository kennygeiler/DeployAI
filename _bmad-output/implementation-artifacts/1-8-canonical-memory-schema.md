# Story 1.8: Canonical memory schema — event log + identity graph + solidified-learning library + tombstones

Status: ready-for-dev

## Story

As a **Data Plane engineer**,
I want a complete Alembic-managed canonical memory schema including the immutable event log, time-versioned identity graph, solidified-learning library with lifecycle states, and tombstone table,
so that every ingested event from Epic 3 has a canonical home and every downstream agent (Epic 6) reads from a stable contract.

**Satisfies:** FR1–3 (event log, identity graph, supersession), FR5 (tombstones), FR8 (retention classes), DP11 (time-versioned identity attributes), NFR74 (expand-contract migrations, canonical memory append-only). Foundations for NFR23 (tenant isolation) — policies land in Story 1.9.

---

## Acceptance Criteria

**AC1.** A single initial Alembic migration under `services/control-plane/alembic/versions/` creates the following tables in the `public` schema on a clean Postgres 16 + `pgvector` database:

- `canonical_memory_events`
- `identity_nodes`
- `identity_attribute_history`
- `identity_supersessions` (the supersession_link pattern — FR3)
- `solidified_learnings`
- `learning_lifecycle_states`
- `tombstones`
- `schema_proposals` (stub surface for Story 1.17)

**AC2.** Every table carries the three mandatory columns:

- `id UUID PRIMARY KEY DEFAULT deployai_uuid_v7()` (UUID v7 — K-sortable, time-ordered per AR's UUID rule)
- `tenant_id UUID NOT NULL`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`

`deployai_uuid_v7()` is a plpgsql function created in the same migration. Postgres 16 has no native `uuidv7()` (landed in Postgres 18); the implementation encodes millisecond-precision timestamp into the high 48 bits + 74 random bits + v7 marker bits, producing monotonically-increasing UUIDs within a millisecond bucket.

**AC3.** `canonical_memory_events` is append-only. A `BEFORE UPDATE OR DELETE` row-level trigger invokes `deployai_forbid_mutation()` which `RAISE EXCEPTION` on any mutation attempt. Both the function and the trigger land in the same migration. Trigger name: `canonical_memory_events_append_only`. Error code: `P0001`; message: `canonical_memory_events is append-only (TG_OP=UPDATE|DELETE)`.

**AC4.** `canonical_memory_events` columns:

```
id              UUID PK          (UUID v7)
tenant_id       UUID NOT NULL
created_at      TIMESTAMPTZ NOT NULL
event_type      TEXT NOT NULL
graph_epoch     BIGINT NOT NULL DEFAULT 0     -- citation envelope schema hint; Story 1.11 wires the actual contract
occurred_at     TIMESTAMPTZ NOT NULL          -- source event time (vs created_at = write time)
source_ref      TEXT                          -- upstream URI (email id, meeting id, etc.); nullable
evidence_span   JSONB NOT NULL DEFAULT '{}'::jsonb
payload         JSONB NOT NULL DEFAULT '{}'::jsonb
```

Index: `idx_canonical_memory_events_tenant_id_created_at (tenant_id, created_at DESC)`.

**AC5.** `identity_nodes` + `identity_attribute_history` satisfy FR2 (one canonical person per node) + DP11 (time-versioned role/title/email):

`identity_nodes`: `id`, `tenant_id`, `created_at`, `canonical_name TEXT NOT NULL`, `primary_email_hash TEXT NOT NULL` (SHA-256 of normalized email — enables lookups without leaking plaintext), `is_canonical BOOLEAN NOT NULL DEFAULT true` (set `false` when merged into another identity via `identity_supersessions`).

`identity_attribute_history`: `id`, `tenant_id`, `created_at`, `identity_id UUID NOT NULL REFERENCES identity_nodes(id)`, `attribute_name TEXT NOT NULL` (one of `role`, `title`, `email`, `display_name`), `attribute_value TEXT NOT NULL`, `valid_from TIMESTAMPTZ NOT NULL`, `valid_to TIMESTAMPTZ` (NULL = current). Index: `idx_identity_attribute_history_identity_valid (identity_id, attribute_name, valid_from DESC)`. A partial-unique constraint ensures at most one open (`valid_to IS NULL`) row per `(identity_id, attribute_name)`.

**AC6.** `identity_supersessions` (FR3 — duplicate-identity resolution):

```
id                          UUID PK
tenant_id                   UUID NOT NULL
created_at                  TIMESTAMPTZ NOT NULL
superseded_identity_id      UUID NOT NULL REFERENCES identity_nodes(id)
canonical_identity_id       UUID NOT NULL REFERENCES identity_nodes(id)
reason                      TEXT NOT NULL
authority_actor_id          UUID
CONSTRAINT different_ids CHECK (superseded_identity_id <> canonical_identity_id)
```

Index: `idx_identity_supersessions_tenant_superseded (tenant_id, superseded_identity_id)`.

**AC7.** `solidified_learnings` carries the shape the epic AC dictates literally:

```
id                      UUID PK
tenant_id               UUID NOT NULL
created_at              TIMESTAMPTZ NOT NULL
belief                  TEXT NOT NULL
evidence_event_ids      UUID[] NOT NULL           -- references canonical_memory_events(id); RLS enforced at read time (Story 1.9)
application_trigger     JSONB NOT NULL DEFAULT '{}'::jsonb
state                   learning_state_t NOT NULL DEFAULT 'candidate'
```

Where `learning_state_t` is a Postgres ENUM type with values `('candidate','solidified','overridden','tombstoned')`. Enum is created in the same migration via `CREATE TYPE`.

`learning_lifecycle_states` tracks every transition append-only:

```
id                      UUID PK
tenant_id               UUID NOT NULL
created_at              TIMESTAMPTZ NOT NULL
learning_id             UUID NOT NULL REFERENCES solidified_learnings(id)
state                   learning_state_t NOT NULL
transitioned_at         TIMESTAMPTZ NOT NULL
actor_id                UUID                          -- user who caused the transition; NULL for system-triggered
reason                  TEXT
```

Index: `idx_learning_lifecycle_states_learning (learning_id, transitioned_at DESC)`.

**AC8.** `tombstones` carries exactly the fields the epic AC dictates (FR5):

```
id                      UUID PK
tenant_id               UUID NOT NULL
created_at              TIMESTAMPTZ NOT NULL
original_node_id        UUID NOT NULL                 -- may reference any of canonical_memory_events/identity_nodes/solidified_learnings; no FK (the referenced row may be destroyed)
retention_reason        TEXT NOT NULL
authority_actor_id      UUID NOT NULL
destroyed_at            TIMESTAMPTZ NOT NULL
signature               BYTEA NOT NULL                -- Ed25519 signature over the tombstone payload
tsa_timestamp           BYTEA                         -- RFC 3161 TSR; populated when Story 1.13 lands
```

Index: `idx_tombstones_tenant_original (tenant_id, original_node_id)`.

**AC9.** `schema_proposals` is a minimal stub so Story 1.17 has a home to land the schema-evolution staging area without another migration reshuffle:

```
id                      UUID PK
tenant_id               UUID NOT NULL
created_at              TIMESTAMPTZ NOT NULL
proposer_actor_id       UUID NOT NULL
proposed_ddl            TEXT NOT NULL
status                  TEXT NOT NULL DEFAULT 'pending'     -- {pending, approved, rejected, applied}
reviewed_at             TIMESTAMPTZ
reviewer_actor_id       UUID
```

No trigger, no enum (intentional — Story 1.17 may redesign).

**AC10.** SQLAlchemy 2.x async declarative-2.0 models live under `services/control-plane/src/control_plane/domain/canonical_memory/` — one module per table (or logical group), all re-exported through `__init__.py`. A shared `Base` at `control_plane/domain/base.py` wires `DeclarativeBase` + `MappedAsDataclass` (optional) + naming conventions. `alembic/env.py` imports the `Base.metadata` as `target_metadata` so future autogenerated migrations see the canonical tables.

**AC11.** Expand-contract CI guardrail (NFR74): `services/control-plane/tests/unit/test_migration_guardrails.py` walks every file in `alembic/versions/`, parses the `upgrade()` and `downgrade()` function bodies, and fails the test when a migration:

1. references any canonical-memory table name (`canonical_memory_events`, `identity_nodes`, `identity_attribute_history`, `identity_supersessions`, `solidified_learnings`, `learning_lifecycle_states`, `tombstones`, `schema_proposals`), **AND**
2. contains `ALTER COLUMN` (via `op.alter_column` or raw SQL), **AND**
3. is not tagged with the literal marker comment `# expand-contract: expand` or `# expand-contract: contract` at the top of the `upgrade()` function.

The initial `CREATE TABLE` migration is naturally exempt (no `ALTER COLUMN`). The test exempts itself via the `20260422_0001_*` filename pattern only for additive `op.create_table`/`op.create_index`/`op.execute(CREATE ...)` calls — it does NOT suppress the `ALTER COLUMN` check.

**AC12.** Integration tests under `services/control-plane/tests/integration/test_canonical_memory_schema.py` use `testcontainers[postgres]` to spin a `pgvector/pgvector:pg16` container, run `alembic upgrade head`, and assert:

1. Happy-path INSERT into every table returns the row with a UUID v7 `id` and populated `created_at`.
2. `UPDATE canonical_memory_events SET payload = ...` raises `psycopg.errors.RaiseException` (or equivalent) with the `P0001` message.
3. `DELETE FROM canonical_memory_events WHERE id = ...` raises the same exception.
4. Two consecutive INSERTs into `canonical_memory_events` produce `id` values where `id2 > id1` byte-wise (verifies UUID v7 ordering).
5. `identity_attribute_history` partial-unique constraint: inserting a second open row for the same `(identity_id, attribute_name)` fails; closing the first (`valid_to = now()`) then opening another succeeds.
6. Inserting into `identity_supersessions` with `superseded == canonical` fails the `different_ids` CHECK.
7. `solidified_learnings.state` rejects a literal `'bogus'` value (enum violation).
8. Lifecycle transition: `INSERT solidified_learnings('candidate') → INSERT learning_lifecycle_states('solidified') → UPDATE solidified_learnings.state='solidified'` works end-to-end.
9. Tombstone with all required fields inserts and its `signature` roundtrips bytea unchanged.

Tests are async (`pytest-asyncio`) and share a module-scoped fixture that creates one container and one schema per test module. The container is tagged via `@pytest.mark.integration` — `pnpm turbo run test` excludes them by default; the new `schema.yml` CI job runs them.

**AC13.** `services/control-plane/pyproject.toml` gains:

- `testcontainers[postgres]>=4.9.0` in `[dependency-groups].dev`
- `psycopg[binary]>=3.2.0` in `[dependency-groups].dev` (asyncpg can't run raw DDL cleanly in a single statement; psycopg sync client is the idiomatic choice for migration test harnesses)
- `[tool.pytest.ini_options].markers` = `["integration: requires a Docker daemon (testcontainers)"]`
- `[tool.pytest.ini_options].addopts` = `-m 'not integration'` so the default `pnpm turbo run test` remains hermetic (unit tests only). CI integration job passes `-m integration` explicitly.

**AC14.** New `.github/workflows/schema.yml` (workflow `name: schema`, job `canonical-memory-schema`):

- Path-filtered: runs on PRs touching `services/control-plane/**`, `infra/compose/postgres/**`, or the workflow itself.
- Ubuntu 24.04, `timeout-minutes: 15`, `concurrency` group per workflow+ref, `permissions: contents: read`, all actions SHA-pinned with `# vX.Y.Z` trailing comment.
- Installs Python 3.13 + uv 0.11.7 (matching `ci.yml`), runs `uv sync --frozen`, then `uv run pytest -m integration tests/integration/` from `services/control-plane/`.
- Uses `services.docker` via the runner's default (testcontainers talks to the host daemon — no special setup needed on `ubuntu-24.04`).
- Uploads the pytest JUnit XML as `schema-junit.xml` on failure (14-day retention).

**AC15.** `.github/workflows/README.md` "Current workflows" table gains a `schema.yml` row. It is **NOT** promoted to required-checks on `main` in this PR — per convention §3 ("default to NOT adding to the required set … promote only after a stabilization window"). A follow-up PR promotes it after one clean week.

**AC16.** `docs/canonical-memory.md` (new, ≤ 200 lines) documents:

- Table inventory with one-line purpose
- The append-only contract (trigger name, error code, rationale)
- UUID v7 rationale + the `deployai_uuid_v7()` function
- Expand-contract migration convention + the `# expand-contract:` marker
- What's coming in Story 1.9 (RLS + envelope encryption) — explicit forward reference

`docs/repo-layout.md` gains a one-paragraph "Story 1.8 landed" entry under the existing epic-1 shipment log, mirroring prior stories' format.

**AC17.** Existing gates stay green:

- `pnpm turbo run lint typecheck test build` → 20/20 (integration tests excluded by default).
- `pnpm install --frozen-lockfile` reproducible.
- `pnpm format:check` clean.
- `make dev && make dev-verify` still passes on a clean checkout (Story 1.7 contract — validated by `compose-smoke.yml`).
- Fixtures schema (Story 1.7) is untouched. Seed data sits in `fixtures.*`; canonical memory sits in `public.*`. No cross-schema FKs.

**AC18.** Scope fence — what this story does **NOT** do (deferred work, not regressions):

- **No RLS policies.** Story 1.9 adds `ALTER TABLE ... ENABLE ROW LEVEL SECURITY` + `CREATE POLICY tenant_rls_<table>` in a separate expand migration.
- **No envelope encryption.** `evidence_span` / `payload` / `private_annotation` remain cleartext; Story 1.9 wraps sensitive-field access through `pgp_sym_encrypt` + KMS.
- **No `TenantScopedSession`.** Query plumbing lands in `services/_shared/tenancy.py` under Story 1.9.
- **No repositories/routes/services.** Models are import-only; no business logic.
- **No RFC 3161 signing wiring.** `tombstones.tsa_timestamp` is nullable; Story 1.13 populates it.
- **No citation envelope contract.** Story 1.11 freezes the Zod+Pydantic shape; `canonical_memory_events.graph_epoch` is a forward-compatible column placeholder.
- **No cross-tenant fuzz.** Story 1.10 builds the fuzz harness against the (by-then-enforced) RLS boundary.
- **No admin UI for `schema_proposals`.** Story 1.17 owns that surface.

---

## Architecture bindings (from `_bmad-output/planning-artifacts/architecture.md`)

- **§Data Architecture:** PostgreSQL 16.x + SQLAlchemy 2.x async + Alembic. Canonical memory lives in the DeployAI-derivatives primary cluster.
- **§Naming conventions (§L346):** snake_case plural tables, snake_case columns, `id UUID v7` PK, `idx_<table>_<columns>` indexes, `tenant_rls_<table>` policy names (reserved for Story 1.9).
- **§NFR74:** expand-contract migrations; canonical memory additive-only at the event-log layer.
- **§UUID v7:** time-ordered K-sortable IDs — all entity IDs use v7, not v4.
- **Service boundary (§L726):** no raw SQL bypassing the tenant-scoped session. Scope-of-this-story caveat: raw migration DDL and the integration-test harness both run pre-tenancy (infrastructure-layer code), so they're naturally exempt from that rule. Application code that queries these tables will land under `services/_shared/tenancy.py` in Story 1.9.

## Previous-story intelligence

- **Story 1.7** put seed fixtures in the `fixtures` schema deliberately so 1.8's `public`-schema migration is unblocked. Keep it that way. The fixtures schema is NOT dropped here — `compose-smoke.yml` still depends on it. A future cleanup can consolidate once 1.9/1.10 land.
- **Story 1.3** installed uv + Python 3.13 + SQLAlchemy 2.0.36 + Alembic 1.14.0 + pytest-asyncio 0.24 in `services/control-plane`. No new Python toolchain bumps in this story — only dev deps.
- **Story 1.7** introduced `make dev-verify` + the `compose-smoke.yml` workflow. The 30-min bring-up budget (NFR77) does not cover Alembic migration runtime yet — this story adds `alembic upgrade head` to the `control-plane` container boot path **in a follow-up** (not now; the compose stack today does not auto-migrate). For Story 1.8 the migration is run manually in dev (`uv run alembic upgrade head` from `services/control-plane/`) and by CI (`schema.yml`).

## File map

Create:

```
services/control-plane/alembic/versions/20260422_0001_canonical_memory_schema.py
services/control-plane/src/control_plane/domain/base.py
services/control-plane/src/control_plane/domain/canonical_memory/__init__.py
services/control-plane/src/control_plane/domain/canonical_memory/events.py
services/control-plane/src/control_plane/domain/canonical_memory/identity.py
services/control-plane/src/control_plane/domain/canonical_memory/learnings.py
services/control-plane/src/control_plane/domain/canonical_memory/tombstones.py
services/control-plane/src/control_plane/domain/canonical_memory/proposals.py
services/control-plane/tests/integration/__init__.py
services/control-plane/tests/integration/conftest.py          # testcontainers fixture
services/control-plane/tests/integration/test_canonical_memory_schema.py
services/control-plane/tests/unit/test_migration_guardrails.py
.github/workflows/schema.yml
docs/canonical-memory.md
```

Modify:

```
services/control-plane/alembic/env.py                         # target_metadata = Base.metadata
services/control-plane/pyproject.toml                         # dev deps + pytest markers/addopts
services/control-plane/uv.lock                                # regenerate via uv sync
.github/workflows/README.md                                   # add schema.yml row
docs/repo-layout.md                                            # "Story 1.8 landed" entry
```

## Testing strategy

**Unit (runs under `pnpm turbo run test`):**

- `test_migration_guardrails.py` — static analysis of `alembic/versions/`. Pure-Python, no DB.
- Existing `test_healthz.py` stays green.

**Integration (runs under `schema.yml`, `-m integration`):**

- `test_canonical_memory_schema.py` — 9 assertions per AC12 against a real Postgres 16 container.

**Why testcontainers over a GitHub `services:` block:** the integration test needs the `pgvector/pgvector:pg16` image (matches prod Postgres dockerfile from Story 1.7) AND needs to run `alembic upgrade head` against a freshly-created database. testcontainers handles container lifecycle + port mapping + cleanup in one place; `services:` would require separate workflow plumbing + health-wait logic that duplicates testcontainers' `wait_for_logs` / `ping` primitives.

## Risks

1. **plpgsql `uuid_v7()` implementation correctness.** Mitigation: integration-test assertion #4 (monotonicity within a millisecond) — catches a broken high-48-bit packing.
2. **testcontainers pulls the pgvector image on every CI run (~130 MB).** Mitigation: `docker/setup-buildx-action` is not required; the default Docker daemon on `ubuntu-24.04` caches images across steps in a single job. Across jobs, the pull is one-shot per runner boot — 15–20s at worst.
3. **Alembic `env.py` + async engine edge case on empty database.** Current `env.py` already handles async. Adding `target_metadata` is additive. No breakage expected.
4. **Partial-unique index on `identity_attribute_history`** uses `WHERE valid_to IS NULL`; Postgres 16 supports partial UNIQUE indexes natively — no issue.

## Out-of-scope deferrals (explicit)

See AC18. Re-stated here for reviewer clarity:

- RLS policies, envelope encryption, `TenantScopedSession`, `@requires_tenant_scope` decorator → **Story 1.9**
- Cross-tenant fuzz harness → **Story 1.10**
- Citation envelope contract + `graph_epoch` semantics → **Story 1.11**
- RFC 3161 TSA signing → **Story 1.13**
- Schema-proposal review UI → **Story 1.17**

---

## Completion notes

- (to be filled by dev)

## Change log

- 2026-04-23: Story context authored (lean mode ~260 lines). Status: ready-for-dev.
