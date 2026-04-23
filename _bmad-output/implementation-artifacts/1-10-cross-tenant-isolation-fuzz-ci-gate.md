# Story 1.10: Cross-tenant isolation fuzz CI gate (NFR52)

Status: ready-for-dev

## Story

As a **security engineer**,
I want a CI-gated fuzz harness that actively attempts unauthorized cross-tenant reads across every canonical-memory table and fails the build on any success,
so that the three-layer isolation contract shipped in Story 1.9 cannot silently regress (NFR52).

**Satisfies:** NFR52 (fuzz-based tenant isolation regression gate), FR72 (tenant isolation), epics.md §Story 1.10. Directly builds on Story 1.9's `TenantScopedSession`, `deployai_app` role, and `tenant_rls_<table>` policies.

---

## Acceptance Criteria

**AC1.** A fuzz harness lives at `services/control-plane/src/control_plane/fuzz/cross_tenant.py` with attack-class generators in `fuzz/attacks.py` and report shape in `fuzz/report.py`; tests + fixtures at `services/control-plane/tests/fuzz/` (`conftest.py`, `test_cross_tenant_harness.py`, `test_cli_production_run.py`). The harness is runnable as a standalone CLI via `python -m control_plane.fuzz.cross_tenant --seed <int> --report <path> --database-url ... --app-user ... --app-password ...` **and** exercised by pytest (`@pytest.mark.fuzz`) against a testcontainer. The CLI path is what CI invokes (gated by `FUZZ_GATE_MODE=production`); pytest invocation is for local dev ergonomics.

> **Note on the original AC1 wording.** The epic draft placed the harness under `tests/fuzz/cross_tenant_fuzz.py` (a pytest-path module invoked via `python -m control_plane.tests.fuzz.cross_tenant_fuzz`). That layout breaks `uv`/`setuptools` packaging — `tests/` is not in the importable source tree for production wheel builds, so a production CLI under `tests/` can't be bundled into the control-plane image for out-of-band audit runs. The File map below (authoritative) moves the harness to `src/control_plane/fuzz/` and keeps the meta-tests in `tests/fuzz/`. `.github/workflows/fuzz.yml` and `services/control-plane/package.json` match the File map.

**AC2.** Seeding fixture provisions **≥ 3 synthetic tenants** (generate UUIDs deterministically from the fuzz seed so local repro is possible) with **≥ 50 rows each** in every canonical-memory table. Table list matches Story 1.9 migration:

```
canonical_memory_events
identity_nodes
identity_attribute_history
identity_supersessions
solidified_learnings
learning_lifecycle_states
tombstones
schema_proposals
```

Seeding runs under a **superuser** connection (direct `postgres` role) to bypass RLS, so the harness has a guaranteed baseline of cross-tenant rows to attack. Each row has `tenant_id` set to one of the three synthetic tenants; seeding **must** be deterministic for a given seed (random inputs only via `random.Random(seed)`).

**AC3.** Attack vectors. The harness runs **≥ 500 fuzzed queries per table** (≥ 4,000 total across 8 tables) from each of the following attack classes, via an **application-level** connection authenticated as `deployai_app` (the non-superuser role the migration provisions, subject to FORCE RLS):

1. **Baseline RLS**: Open a `TenantScopedSession` for tenant A, issue `SELECT * FROM <table> WHERE id = '<B-owned-row-id>'` — expect 0 rows.
2. **No-scope read**: Open a raw `AsyncSession` with no `SET LOCAL app.current_tenant`, attempt `SELECT * FROM <table>` — expect 0 rows (GUC-missing fails closed).
3. ~~**GUC override mid-transaction**~~ — **intentionally omitted** from the gating set after implementation. Any connected role may issue `SET LOCAL app.current_tenant`, so the DB itself cannot refuse the override; the only possible defense is the application-level `@requires_tenant_scope` contextvar guard at function-entry. A raw-SQL fuzz harness cannot meaningfully exercise that guard. The limitation is called out explicitly in `docs/security/cross-tenant-fuzz.md` under *Not covered*. Gating coverage is 6 classes (1, 2, 4, 5, 6, 7).
4. **`SET ROLE` / `SET SESSION AUTHORIZATION` escalation**: Issue `SET ROLE postgres`, `SET SESSION AUTHORIZATION postgres`, `RESET ROLE`, `SET LOCAL ROLE ...` — expect `ERROR: permission denied` (SQLSTATE `42501`). `deployai_app` is `NOINHERIT` and is **not** granted superuser/BYPASSRLS, so every escalation attempt must error.
5. **ORM escape hatches**: Use `session.execute(text("SELECT ..."))` with literal string tenant IDs injected (no bind params), `session.connection()`, `conn.exec_driver_sql(...)` — every path still runs under the same transaction's `SET LOCAL`, so RLS still applies. Expect 0 rows for cross-tenant reads.
6. **Cross-tenant write**: Under `TenantScopedSession(B)`, attempt `INSERT INTO <table> (tenant_id, ...) VALUES (:A_id, ...)` and `UPDATE <table> SET tenant_id = :A_id WHERE id = :B-owned`. Expect SQLSTATE `42501` (WITH CHECK violation) for every row; the harness treats any successful insert/update as a FAIL.
7. **SQL injection via string-concat tenant_id**: Build queries like `SELECT * FROM <table> WHERE tenant_id = '\\x55' OR '1'='1'` and variants (`--`, `/* */`, `UNION SELECT ... FROM <table> WHERE tenant_id = '<B-id>'`). Expect 0 rows or a parse error; rows belonging to a tenant other than the scoped one is a FAIL.
8. **Covering indexes / statistics leak** (sanity check, not a hard gate): run `EXPLAIN (ANALYZE, BUFFERS) SELECT ... FROM <table>` under tenant A and assert the plan's `rows` estimate reflects only A's partition. Mark as `info` severity in the report; do not fail the build on this alone.

The harness records **one event per attempt** (see AC5) regardless of attack class.

**AC4.** Any successful cross-tenant read or write fails the CI job with a non-zero exit code and a precise diagnostic containing: (a) attack class number, (b) tenant under scope, (c) tenant whose row leaked, (d) table, (e) offending SQL, (f) the exact row(s) returned. The diagnostic is deterministic for a given seed so maintainers can reproduce locally.

**AC5.** Structured JSON report written to `artifacts/fuzz/cross-tenant-report.json`. Shape:

```json
{
  "seed": 1742847291,
  "started_at": "2026-04-24T09:00:00Z",
  "finished_at": "2026-04-24T09:04:11Z",
  "postgres_version": "16.3",
  "tenants": ["00000000-0000-7000-8000-...", "..."],
  "tables": {
    "canonical_memory_events": {
      "seeded_rows_per_tenant": 50,
      "attempts_per_attack_class": {"1": 80, "2": 60, "3": 60, "4": 60, "5": 60, "6": 100, "7": 80},
      "failures": [],
      "duration_ms": 1234
    },
    "...": {}
  },
  "totals": {"attempts": 4800, "failures": 0, "duration_ms": 45123},
  "result": "pass"
}
```

`failures` is an array of `{attack_class, tenant_under_scope, leaked_tenant, sql, rows_returned}` objects; empty on success. `result` is `"pass"` only when `totals.failures == 0`.

**AC6.** CI workflow `.github/workflows/fuzz.yml` runs the harness on every PR touching `services/**`, `services/_shared/tenancy/**`, or `services/control-plane/alembic/versions/**`. Structure mirrors `schema.yml` (spins up `pgvector/pgvector:pg16` as a service, installs `uv`, runs migrations, executes the harness). The workflow uploads `artifacts/fuzz/cross-tenant-report.json` as a retained artifact (14 days) on every run (both pass and fail — auditors need the evidence trail). `fuzz.yml` is **not** added to the required-checks set yet — per `.github/workflows/README.md` §3 convention, a new workflow bakes for one stabilization window before promotion.

**Note re epics AC5 wording:** The AC mentions `packages/tenancy/*`; the actual path is `services/_shared/tenancy/**` (that naming was chosen in Story 1.9). Workflow path filters must use the real path.

**AC7.** Turbo task wiring. `services/control-plane/package.json` exposes a `fuzz:cross-tenant` script:

```json
"fuzz:cross-tenant": "uv run python -m control_plane.fuzz.cross_tenant --seed ${FUZZ_SEED:-$GITHUB_RUN_ID} --report ../../artifacts/fuzz/cross-tenant-report.json"
```

`turbo.json` gets a new task:

```json
"fuzz:cross-tenant": {
  "cache": false,
  "env": ["FUZZ_SEED", "DATABASE_URL"],
  "outputs": ["artifacts/fuzz/**"]
}
```

Then `pnpm turbo run fuzz:cross-tenant` in CI invokes it end-to-end.

**AC8.** Documentation at `docs/security/cross-tenant-fuzz.md`. Contents:

- **Purpose** — what regression this gate catches (any change that lets `deployai_app` read/write outside its scope).
- **Attack surface** — enumerate the 8 attack classes from AC3 with one-sentence rationale each.
- **Report format** — sample JSON and field-by-field meaning.
- **Local repro** — `FUZZ_SEED=<num> pnpm turbo run fuzz:cross-tenant` and `DATABASE_URL=...` expectations.
- **When this gate fails, what to do** — triage flow: `(1)` re-run locally with the seed from the failing CI run; `(2)` inspect `failures[0]` in the JSON; `(3)` add a targeted integration test under `test_tenant_isolation.py` before fixing; `(4)` fix. Explicitly: **never** widen the harness to work around a failure — failures are always real regressions until proven fixture-bugs, and fixture bugs still require a failing test first.
- **Known non-hermetic cases** — the `EXPLAIN` plan check is flaky under high Postgres autovacuum load and is `info` severity only.

**AC9.** Performance budget. Full harness runtime ≤ **10 minutes** wall-clock on a GitHub-hosted `ubuntu-24.04` runner with the default 2-core config. If we exceed this in tuning, halve the per-table attempt count down to the AC minimum (≥ 500/table) before considering parallelism — correctness trumps speed. The fixture seeding step is capped at 60 s; the attack loop is capped at 9 min.

**AC10.** Test quality. Every attack class in AC3 has at least one unit-style assertion in `tests/fuzz/test_cross_tenant_harness.py` that runs against a minimal in-memory or testcontainer Postgres and proves: (a) a correctly-isolated baseline passes, (b) a deliberately-weakened schema (RLS disabled on one table, injected via a fixture) fails with a report that correctly fingers the broken table. This anti-test is what we'd lose if the harness broke silently.

---

## Architecture bindings

- Architecture.md §NFR52: "cross-tenant isolation fuzz runs in CI on every PR touching canonical memory or tenancy primitives; any successful cross-tenant read fails the gate"
- Architecture.md §NFR23 (Story 1.9): the three-layer defense this harness attacks
- `services/_shared/tenancy/` (Story 1.9): re-use `TenantScopedSession`, `@requires_tenant_scope`
- `services/control-plane/alembic/versions/20260422_0002_tenant_rls_policies.py` (Story 1.9): the policies under test and the `deployai_app` role the harness authenticates as
- `.github/workflows/schema.yml` (Story 1.8): template for `fuzz.yml` layout
- Existing `tests/integration/test_tenant_isolation.py` (Story 1.9): pattern for testcontainer + app-role connection fixtures (`_configure_app_role`, `_async_url_for`, `app_engine`)

---

## File map

**New:**

- `services/control-plane/src/control_plane/fuzz/__init__.py` — package marker
- `services/control-plane/src/control_plane/fuzz/cross_tenant.py` — harness implementation + `__main__` entrypoint
- `services/control-plane/src/control_plane/fuzz/report.py` — JSON report builder + schema (dataclass, no extra deps)
- `services/control-plane/src/control_plane/fuzz/attacks.py` — the 8 attack-class generators (parameterized by seed + tenant list + table)
- `services/control-plane/tests/fuzz/__init__.py`
- `services/control-plane/tests/fuzz/conftest.py` — testcontainer + seed fixtures (extend, don't duplicate, the `postgres_engine` / `app_engine` fixtures from `tests/integration/conftest.py`)
- `services/control-plane/tests/fuzz/test_cross_tenant_harness.py` — AC10 anti-tests
- `.github/workflows/fuzz.yml`
- `docs/security/cross-tenant-fuzz.md`

**Modified:**

- `services/control-plane/package.json` — add `fuzz:cross-tenant` script
- `services/control-plane/pyproject.toml` — add `fuzz` pytest marker; ensure `control_plane.fuzz` is packaged
- `turbo.json` — add `fuzz:cross-tenant` task
- `_bmad-output/implementation-artifacts/sprint-status.yaml` — flip `1-10-cross-tenant-isolation-fuzz-ci-gate` → `in-progress` at dev kickoff, `done` at merge

---

## Testing strategy

- **Unit** (hermetic, no DB): `tests/fuzz/test_cross_tenant_harness.py` mounts a stub executor that simulates RLS (returns `[]` for cross-tenant reads, raises `InsufficientPrivilege` for cross-tenant writes) and proves the harness flags a deliberately-weakened stub as a failure.
- **Integration** (real Postgres via testcontainers): the full harness runs as `-m fuzz` and is excluded from the default pytest run (`addopts = -m 'not integration and not fuzz'`). CI invokes it separately.
- **Anti-test**: one test in `test_cross_tenant_harness.py` monkeypatches the migration to disable RLS on `canonical_memory_events`, runs the harness, and asserts `result == "fail"` and the failure record names the right table. This is the harness's own regression guard.

---

## Risks & out-of-scope

**Risks:**

- **R1. Seed non-determinism.** UUIDv7 in the real schema embeds wall-clock time; the harness **must not** rely on UUIDv7 for seed-derived IDs — use random UUIDs from `random.Random(seed)` for fixture rows, and pull real rows' IDs back by `SELECT id FROM <table> WHERE tenant_id = :tid LIMIT 50` after seed-insert. Document this in `cross_tenant.py`.
- **R2. Fuzzer false-positives from empty tables.** If a seeding bug leaves a table empty for tenant B, "0 rows returned when reading B's rows as A" looks like a correct isolation pass when it's actually seed skew. Mitigation: assert `count(*) == seeded_rows_per_tenant * 3` per table under a superuser connection before the attack loop starts; fail fast with a seeding error if not.
- **R3. `SET ROLE` noise.** `deployai_app` being `NOINHERIT` means `SET ROLE` to any granted role (none yet, but forward-compatible) would succeed but not grant bypass. Harness must distinguish "role switch succeeded but queries still RLS'd" (pass) from "role switch succeeded and queries now see other tenants" (fail). The reporter records the attempted role and the observed behavior.
- **R4. CI runner resource skew.** A 2-core ubuntu runner running Postgres + 4,000 queries + JSON reporting may push 10 min. If exceeded, follow AC9: cut to the AC-minimum 500 attempts/table; do not reduce attack-class coverage.

**Out of scope** (explicitly deferred):

- **OOS1. Fuzzing the `KMSEnvelopeDEKProvider`** — that provider doesn't exist yet (Story 3.x). This gate only covers the RLS + `TenantScopedSession` pair.
- **OOS2. Multi-session concurrency attacks** (e.g., two simultaneous `TenantScopedSession`s racing on the same connection pool slot). Covered later when the connection-pool strategy lands (Story 2.x). The `asyncio.Lock`-based isolation in `TenantScopedSession` is single-connection correct today.
- **OOS3. Timing-side-channel attacks** (did a cross-tenant row exist? infer from query latency). Out of scope for NFR52; architecturally addressed by partitioning planned for Epic 3.
- **OOS4. Application-layer fuzzing** (HTTP handlers, request replays). This story fuzzes the DB boundary; Story 2.x owns the HTTP boundary.
- **OOS5. Promoting `fuzz.yml` to a required check.** Bakes for ≥ 1 week on main first — per `.github/workflows/README.md` §3 convention.

---

## Completion notes

- Harness shipped at `src/control_plane/fuzz/{cross_tenant,attacks,report}.py` (AC1 path correction above).
- 6 gating attack classes (1, 2, 4, 5, 6, 7). Class 3 (GUC override) intentionally omitted — application-layer defense only, cannot be meaningfully exercised by a raw-SQL fuzzer.
- CI workflow runs three concentric rings: meta-tests (harness validation) → anti-test (`DISABLE ROW LEVEL SECURITY` proves harness still catches leaks) → `FUZZ_GATE_MODE=production` CLI run at AC-minimum scale (≥4,000 attempts, writes audit-trail JSON to `artifacts/fuzz/cross-tenant-report.json`).
- Review round-1 findings applied:
  - `attack_cross_tenant_write` now raises a sentinel on successful INSERT so the savepoint rolls back — no persisted leaks in CI or in local repro.
  - Blast-radius count on successful INSERT is read through the root (superuser) engine so RLS doesn't mask the count.
  - `attack_set_role_escalation` reports a successful escalation as a finding even when the follow-up SELECT returns zero rows; adds `RESET ROLE` + `RESET SESSION AUTHORIZATION` in a `finally` to prevent pool pollution.
  - Pre-flight check refuses to seed if fuzz tenant UUIDs already exist in any canonical table (guards against pointing the CLI at a shared DB).
  - `_derive_app_url` switched from string-surgery to `sqlalchemy.engine.make_url` so passwords with `@`, `:`, `/`, `#` round-trip correctly.
  - `main()` rejects empty `--app-password` (prevents accidental `trust`-auth drift).
  - CLI prints the first 3 `failures[]` entries to stderr on fail (AC4 diagnostic now visible in workflow logs, not just the JSON artifact).
  - CLI reads `FUZZ_SEED` env var as the default for `--seed` so `pnpm turbo run fuzz:cross-tenant` honours AC7 seed propagation without JSON-script shell expansion.
  - Autouse TRUNCATE fixture added to `tests/fuzz/conftest.py` — rows no longer accumulate across meta-tests.
  - Traceback printed on harness error (not just the message) so CI triage of seed-regression bugs is tractable.

## Change log

- 2026-04-23: Story context authored (lean mode ~260 lines). Status: ready-for-dev.
- 2026-04-23: Implementation landed; review round-1 applied (13 patches across attacks, harness, CI workflow, docs). Six gating attack classes, production-weight CLI run gated behind `FUZZ_GATE_MODE=production` in CI. AC1 wording corrected to match the `src/control_plane/fuzz/` layout (prior `tests/fuzz/cross_tenant_fuzz.py` wording was internally inconsistent with the File map and breaks `uv` packaging).
