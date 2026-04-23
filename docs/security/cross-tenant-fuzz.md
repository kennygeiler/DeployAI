# Cross-tenant isolation fuzz gate

**Story:** 1.10 · **Satisfies:** NFR52 · **Related:** [tenant-isolation.md](tenant-isolation.md) (Story 1.9 three-layer defense)

## Purpose

This CI gate actively attempts unauthorized cross-tenant reads and writes against every canonical-memory table. Any successful leak fails the build.

The point is regression-catching, not discovery: Story 1.9 builds the three-layer isolation (`TenantScopedSession` → Postgres RLS → envelope encryption). The fuzz harness is what stops a future refactor (a stray `session.execute(text(...))` in application code, a dropped RLS policy in a migration, a misconfigured role grant) from silently breaking that contract.

## Attack surface

Six attack classes, each run **≥ 500 times per table** across 3 synthetic tenants × 8 canonical tables (~4,000 attempts per run):

| # | Name | Vector | Expected outcome |
|---|------|--------|------------------|
| 1 | `baseline_rls_read` | Under tenant A's scope, `SELECT` a specific B-owned row id | 0 rows (RLS filters) |
| 2 | `no_scope_read` | Raw connection, no `SET LOCAL app.current_tenant` | 0 rows (policy `current_setting(…, true)` is NULL → fails closed) |
| 4 | `set_role_escalation` | `SET ROLE postgres`, `SET SESSION AUTHORIZATION postgres`, `SET LOCAL ROLE …` | SQLSTATE `42501` (`deployai_app` is `NOINHERIT` and has no BYPASSRLS-bearing memberships) |
| 5 | `orm_escape_text_literal` | `session.execute(text("… WHERE tenant_id = '<B-id>'"))` — no bind params | 0 rows (RLS applies regardless of how the ORM composed the query) |
| 6 | `cross_tenant_write` | Under B's scope, `INSERT INTO <table> (tenant_id, …) VALUES ('<A-id>', …)` | SQLSTATE `42501` (WITH CHECK violation) |
| 7 | `sql_injection` | Classic SQLi payloads (`' OR '1'='1`, `UNION SELECT …`, `--` comments) smuggled into WHERE clauses | 0 cross-tenant rows (parser typically rejects; RLS catches what slips through) |

Class **3 (`guc_override`)** is intentionally absent. At the raw-DB layer, any connected role may issue `SET LOCAL app.current_tenant`, so the database itself cannot refuse the override; the only defense is the application-level `@requires_tenant_scope` contextvar guard at function-entry. A raw-SQL fuzz harness cannot exercise that guard, so including the class would produce guaranteed false positives. See *Not covered* below.

The 8th class sketched in the architecture doc — `EXPLAIN (ANALYZE, BUFFERS)` plan-row-count sanity check — is **deferred, not implemented**. Pg-runner timing sensitivity + autovacuum state make the estimate too flaky to gate on, and a flaky gate is worse than no gate. Revisit when Epic 3 partitioning lands and plans become deterministic per-tenant.

## Report format

Written to `artifacts/fuzz/cross-tenant-report.json` on every run (pass and fail both — auditors need the evidence trail either way). Retention is 14 days on the CI artifact.

```json
{
  "seed": 20260423,
  "started_at": "2026-04-23T09:00:00+00:00",
  "finished_at": "2026-04-23T09:04:11+00:00",
  "postgres_version": "16.3",
  "tenants": ["66757a7a-0000-7000-8000-000000000000", "…"],
  "tables": {
    "canonical_memory_events": {
      "seeded_rows_per_tenant": 50,
      "attempts_per_attack_class": {"1": 84, "2": 83, "4": 83, "5": 83, "6": 84, "7": 83},
      "failures": [],
      "duration_ms": 3421
    }
  },
  "totals": {"attempts": 4000, "failures": 0, "duration_ms": 27834},
  "result": "pass"
}
```

Failure records include: `attack_class`, `attack_name`, `tenant_under_scope`, `leaked_tenant`, `table`, `sql`, `rows_returned` (first 3 rows, `repr()`-stringified — we never persist full rowsets so a compromised CI log never becomes a data-exfiltration channel).

## Local repro

```bash
# From repo root — spin up Postgres, migrate, fuzz.
docker run --rm -d --name fuzz-pg \
  -e POSTGRES_USER=deployai -e POSTGRES_PASSWORD=deployai-test \
  -e POSTGRES_DB=deployai -p 5432:5432 \
  pgvector/pgvector:pg16

cd services/control-plane
export DATABASE_URL="postgresql+psycopg://deployai:deployai-test@localhost:5432/deployai"
uv run alembic upgrade head
psql "$DATABASE_URL" -c "ALTER ROLE deployai_app WITH LOGIN PASSWORD 'deployai-fuzz-local'"

export FUZZ_APP_USER=deployai_app
export FUZZ_APP_PASSWORD=deployai-fuzz-local
export FUZZ_SEED=20260423  # copy from the failing CI run

cd ../..
pnpm turbo run fuzz:cross-tenant
# → artifacts/fuzz/cross-tenant-report.json
```

## When this gate fails

1. **Do not work around it.** Failures are real regressions until proven otherwise — even the anti-test that validates the harness ensures we catch silent self-breakage.
2. **Copy the seed** from the failing CI run's workflow env (`FUZZ_SEED`) and repro locally with the commands above.
3. **Inspect `failures[0]`** in the JSON. The `sql` field is the exact offending query; `attack_class` tells you which defense broke (see the table above).
4. **Write a failing test first.** Add a targeted case to `services/control-plane/tests/integration/test_tenant_isolation.py` that reproduces the specific leak. This locks in the invariant against future regressions beyond the fuzz loop's probabilistic coverage.
5. **Fix the cause, not the symptom.** If a migration dropped a policy, restore it. If an application call path bypassed `@requires_tenant_scope`, add the decorator and a call-site lint rule. The fuzz harness itself is never the thing to change in response to a failure.

## Known non-hermetic cases

- **`set_role_escalation` to future BYPASSRLS roles** — today `deployai_app` has no memberships in BYPASSRLS-bearing roles, so every escalation attempt errors at `SET ROLE`. When Story 2.4 adds new application roles (read-only reporter, etc.), this attack class will need updating to include those as additional escalation targets. The harness already records *any* successful escalation as a finding (even with zero rows returned), so a future role regression is caught the first time it ships.

## Not covered (explicitly)

- **GUC-override attack (attack class 3)** — `SET LOCAL app.current_tenant` is not an ACL-gated operation in Postgres; any connected role can change it. The defense lives in the application (`@requires_tenant_scope` checks scope on function-entry, `TenantScopedSession`'s contextvar catches nested cross-tenant entries). The fuzz harness speaks raw SQL and cannot exercise those Python-layer guards, so attack class 3 would produce guaranteed false positives and has been removed from the gating set. A separate unit-test at `services/_shared/tenancy/tests/unit/test_session.py` already covers the contextvar-based cross-tenant-nesting detection that would catch a mid-flight scope swap in real application code.
- **AWS KMS-backed DEK fuzzing** — deferred to Story 3.x when the KMS provider lands.
- **Multi-session concurrency races** on the connection pool — covered by Story 2.x when pooling ships.
- **Timing side channels** — architecturally addressed by Epic 3 partitioning, not this gate.
- **HTTP-layer fuzzing** — Story 2.x owns the request boundary; this gate fuzzes the DB boundary only.

## Promotion to required check

`fuzz.yml` bakes on `main` for ≥ 1 green week before promotion to the required-checks set (`.github/workflows/README.md` §3). Until then, a red fuzz run is visible on the PR but does not block merge — intentionally, so the first weeks of shakedown don't spuriously wedge development.
