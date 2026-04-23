# Story 1.9: Three-layer tenant isolation (RLS + TenantScopedSession + envelope-encryption pattern)

Status: ready-for-dev

## Story

As a **security engineer**,
I want every canonical-memory table protected by Postgres RLS, every SQLAlchemy session forced through a tenant-scoping context manager, and a DEK-based envelope-encryption path wired for sensitive fields,
so that cross-tenant reads are architecturally impossible and NFR23 is enforced at three independent layers.

**Satisfies:** NFR23 (three-layer tenant isolation), FR72 (tenant isolation), architectural §L181–184. Foundation for NFR52 (Story 1.10 fuzz harness attacks this exact boundary).

---

## Acceptance Criteria

**AC1.** A new Python package `services/_shared/tenancy/` is the **single source of truth** for tenant-scoping primitives. It ships as an editable uv workspace package (`deployai-tenancy`) with:

- `pyproject.toml` (PEP 621, `name = "deployai-tenancy"`, Python 3.13, SQLAlchemy 2.x peer dep).
- `src/deployai_tenancy/__init__.py` re-exports the public surface.
- `src/deployai_tenancy/session.py` — `TenantScopedSession` async context manager (see AC2).
- `src/deployai_tenancy/decorators.py` — `@requires_tenant_scope` (see AC3).
- `src/deployai_tenancy/envelope.py` — `DEKProvider` protocol + `InMemoryDEKProvider` + `encrypt_field()`/`decrypt_field()` (see AC5).
- `src/deployai_tenancy/errors.py` — `MissingTenantScope`, `IsolationViolation`, `DEKUnavailable` exceptions.
- `tests/unit/test_*.py` — hermetic unit tests (no DB).

`services/control-plane/pyproject.toml` declares `deployai-tenancy` as an editable path dep: `deployai-tenancy = { path = "../_shared/tenancy", editable = true }`. uv workspaces resolve the package without publishing to PyPI.

**AC2.** `TenantScopedSession(tenant_id: UUID, engine: AsyncEngine) -> AsyncContextManager[AsyncSession]`:

1. Raises `MissingTenantScope` on entry if `tenant_id is None` or not a `uuid.UUID`.
2. Opens an `AsyncSession` bound to `engine`.
3. Before yielding, issues `SET LOCAL app.current_tenant = :tid` in the same transaction.
4. Yields the session to the caller.
5. On exit (normal or exception), commits or rolls back; the `SET LOCAL` is scoped to the transaction so it evaporates automatically.

The session object carries `.tenant_id: UUID` and `.is_tenant_scoped: True` attributes so `@requires_tenant_scope` can validate at call time.

Unit tests assert:

- Entering with `tenant_id=None` raises `MissingTenantScope`.
- Entering with a string instead of `UUID` raises `MissingTenantScope`.
- On success, `session.info["tenant_id"] == tenant_id` and `session.info["is_tenant_scoped"] is True`.
- Nested `TenantScopedSession` contexts for different tenants raise `IsolationViolation` at inner entry.

**AC3.** `@requires_tenant_scope` decorator wraps any async function whose first argument (after `self` if bound) is an `AsyncSession`:

- Inspects the session's `.info` dict for `is_tenant_scoped`; raises `MissingTenantScope` if absent or falsy.
- Preserves the wrapped function's name, docstring, type annotations (`functools.wraps`).
- Works on both free functions and bound methods.
- Unit tests: decorator rejects a vanilla `AsyncSession`; accepts a `TenantScopedSession`-minted one; preserves the signature through `inspect.signature`.

**AC4.** Alembic migration `services/control-plane/alembic/versions/20260422_0002_tenant_rls_policies.py` (tagged `# expand-contract: expand`):

1. Enables RLS on every canonical-memory table (`canonical_memory_events`, `identity_nodes`, `identity_attribute_history`, `identity_supersessions`, `solidified_learnings`, `learning_lifecycle_states`, `tombstones`, `schema_proposals`) via `ALTER TABLE <t> ENABLE ROW LEVEL SECURITY`.
2. Also `ALTER TABLE <t> FORCE ROW LEVEL SECURITY` so the table owner is NOT exempted (critical — without this, the DB role that runs migrations can still read everything).
3. Creates policy `tenant_rls_<table>` per table: `USING (tenant_id = current_setting('app.current_tenant', true)::uuid) WITH CHECK (tenant_id = current_setting('app.current_tenant', true)::uuid)`. The `true` second arg to `current_setting` returns NULL if the GUC is unset, so queries without a scope return zero rows (fail-closed) rather than erroring.
4. Creates a `deployai_app` role (if not exists) with `LOGIN NOINHERIT` and grants `SELECT, INSERT, UPDATE, DELETE` on all canonical tables — the role application code uses. Migration-running role (`postgres` superuser) bypasses RLS only because FORCE is off for it, BUT for app-code safety the connection pool uses `deployai_app`.
5. `downgrade()` drops the policies and disables RLS (for test rollback), tagged `# expand-contract: contract`.

**Note:** For Story 1.9 the connection URL used by control-plane remains `postgres` superuser (one service, single env). A follow-up (Story 2.4 — tenant-scoped session store) swaps to `deployai_app`. The policies land now so the fuzz harness (Story 1.10) has a real boundary to attack.

**AC5.** Envelope-encryption path (`src/deployai_tenancy/envelope.py`):

- `DEKProvider` is a `Protocol` with `async def get_dek(tenant_id: UUID) -> bytes` returning a 32-byte key.
- `InMemoryDEKProvider` — dev-mode implementation that derives a deterministic key from `tenant_id` + a hardcoded dev-mode pepper. Raises on `ENVIRONMENT != "dev"`.
- `encrypt_field(plaintext: bytes, dek: bytes) -> bytes` wraps `pgcrypto`'s `pgp_sym_encrypt_bytea()` via a parameterized SQL call executed through the provided async session. Returns the ciphertext bytea as Python `bytes`.
- `decrypt_field(ciphertext: bytes, dek: bytes) -> bytes` — the inverse.
- Both helpers require a `TenantScopedSession`-minted `AsyncSession` (enforced by `@requires_tenant_scope`).

The **real AWS-KMS-backed** `DEKProvider` (`KMSEnvelopeDEKProvider` that uses `boto3` + `GenerateDataKey` + KMS envelope decrypt) is explicitly deferred to **Story 3.x** when AWS infra is provisioned. The protocol + in-memory implementation + tests exercise the full envelope flow locally so the interface is frozen now.

**AC6.** Integration tests (`services/control-plane/tests/integration/test_tenant_isolation.py`, `-m integration`) against a real Postgres via `testcontainers[postgres]`:

1. **Happy path**: open `TenantScopedSession(tenant_id=A)`, insert rows across all 8 canonical tables, read them back, all visible.
2. **Cross-tenant read blocked by RLS**: insert row under tenant A, open `TenantScopedSession(tenant_id=B)`, `SELECT * FROM canonical_memory_events WHERE id = <A's row>` returns zero rows (RLS filters silently — standard Postgres behavior).
3. **Cross-tenant write blocked by WITH CHECK**: open `TenantScopedSession(tenant_id=B)`, attempt `INSERT ... (tenant_id=A, ...)`. The `WITH CHECK` policy raises `psycopg.errors.InsufficientPrivilege`.
4. **No-scope query blocked**: open a raw `AsyncSession` (no `SET LOCAL`), `SELECT * FROM canonical_memory_events` returns zero rows (because `current_setting('app.current_tenant', true)` is NULL — policy fails closed).
5. **Envelope encryption round-trip**: `encrypt_field(b"secret", dek) → decrypt_field(ct, dek) == b"secret"` through a `TenantScopedSession`.
6. **FORCE RLS**: the migration-owner role (even as superuser-equivalent) receives zero rows when reading without a scope — proves `FORCE ROW LEVEL SECURITY` is on. Note: `postgres` superuser still bypasses RLS via the `BYPASSRLS` attribute; this test uses the `deployai_app` role the migration creates to prove the non-superuser path is covered.

Skip on environments lacking Docker (`pytest.importorskip('testcontainers')`).

**AC7.** Unit tests (`services/_shared/tenancy/tests/unit/test_*.py`, runs under `pnpm turbo run test`):

- `test_session.py` — AC2 assertions (no DB; mocks `AsyncEngine` + `AsyncSession`).
- `test_decorators.py` — AC3 assertions.
- `test_envelope.py` — `InMemoryDEKProvider` determinism; `encrypt_field(decrypt_field(ct, dek), dek) == plaintext` using a stub SQL executor; `InMemoryDEKProvider` raises in `ENVIRONMENT=prod`.
- `test_errors.py` — exception-type hierarchy.

**AC8.** `services/control-plane/src/control_plane/db.py` (new, small — ~30 lines) exposes:

- `get_engine() -> AsyncEngine` — cached singleton reading `DATABASE_URL` from env.
- `tenant_session(tenant_id: UUID) -> TenantScopedSession` — thin wrapper over `TenantScopedSession(tenant_id, get_engine())` so control-plane code doesn't re-import the shared package's constructor.

This keeps control-plane free of explicit `TenantScopedSession` imports; services outside control-plane can still import directly from `deployai_tenancy`.

**AC9.** `schema.yml` workflow (from Story 1.8) picks up the new integration test automatically (it runs `uv run pytest -m integration tests/integration/`). No workflow file change needed — the new `test_tenant_isolation.py` sits under the same directory and is tagged `@pytest.mark.integration` via the file-level marker or `[tool.pytest.ini_options].markers` pattern established in 1.8.

**AC10.** `.github/workflows/ci.yml` — the `Smoke` job runs the shared package's unit tests by adding `services/_shared/tenancy` to the `pytest` invocation. Implementation: control-plane's existing `uv run pytest` call (inside the Smoke job) already discovers unit tests in the control-plane tree; the shared package's unit tests run via a second invocation `uv run --project services/_shared/tenancy pytest services/_shared/tenancy/tests/` or via a workspace-level `pytest` if uv workspace is set up. The pragmatic approach: add `uv run --package deployai-tenancy pytest` to the control-plane smoke step (uv workspace member syntax) — since control-plane declares `deployai-tenancy` as a path dep, the workspace is implicit.

Actual implementation: add a `[tool.uv.sources]` entry in control-plane's pyproject pointing at the `_shared/tenancy` path, and add `services/_shared/tenancy/tests` to control-plane's `pytest` discovery roots via `[tool.pytest.ini_options].testpaths = ["tests", "../_shared/tenancy/tests/unit"]`. That way one `uv run pytest` invocation from control-plane covers both surfaces.

**AC11.** `docs/security/tenant-isolation.md` (new, ≤ 200 lines) documents:

- The three layers (app/DB/encryption) with a one-paragraph rationale each.
- `TenantScopedSession` + `@requires_tenant_scope` usage snippets.
- RLS policy naming (`tenant_rls_<table>`) + the `FORCE ROW LEVEL SECURITY` choice.
- The fail-closed semantics of `current_setting('app.current_tenant', true)::uuid`.
- Envelope-encryption state: pattern + in-memory DEK live now; AWS KMS lands Story 3.x.
- Forward reference to Story 1.10's fuzz harness.

`docs/canonical-memory.md` gets a line-level update: the "Story 1.9 will add RLS" forward reference is replaced with "RLS enforced by Story 1.9 (`tenant_rls_<table>` policies; see docs/security/tenant-isolation.md)".

`docs/repo-layout.md` gains a "Story 1.9 landed" entry mirroring prior stories.

**AC12.** Existing gates stay green:

- `pnpm turbo run lint typecheck test build` — all tasks still pass (control-plane lint/typecheck/test now covers both the control-plane tree AND the shared package's unit tests; build is still python-module compilation).
- `pnpm install --frozen-lockfile` — reproducible.
- `pnpm format:check` — clean.
- `pnpm turbo run build` via uv — tenancy package `py_compile` passes.
- `make dev && make dev-verify` — Story 1.7's compose stack still boots clean. The new migration runs automatically when the control-plane container does `alembic upgrade head` on boot (note: 1.7's compose stack does not currently auto-migrate; manual `uv run alembic upgrade head` in dev is the pattern — unchanged from 1.8). `compose-smoke.yml` is NOT affected because it does not touch the `public` schema with application queries.

**AC13.** Scope fence — what this story does **NOT** do:

- **No AWS KMS integration.** `KMSEnvelopeDEKProvider` class is referenced as an interface target but not implemented. Story 3.x.
- **No fuzz harness.** Story 1.10 builds it.
- **No DEK rotation.** Story 12.x (NFR76 — 90-day rotation).
- **No cross-service tenancy injection.** `apps/web` session → API does not yet propagate tenant context; Story 2.4 (tenant-scoped session store) owns that.
- **No `deployai_app` role swap.** The migration creates the role, but control-plane still connects as the superuser. Story 2.4 flips the default.
- **No encrypted columns on existing tables.** `evidence_span` remains JSONB plaintext; the encryption path exists as helpers only, applied column-by-column in later stories (`private_annotation` → Epic 10, `raw_transcript_content` → Epic 11). Story 1.9 ships the **mechanism**, not the column migrations.

---

## Architecture bindings

- **§L181–184 (three-layer defense):** App = `TenantScopedSession`; DB = RLS policies; Encryption = envelope pattern with per-tenant DEK.
- **§NFR23:** tested at three layers; failure at any one layer alone does not cause a cross-tenant read.
- **§L352 (naming):** `tenant_rls_<table>` policy names. No deviation.
- **§L476 (service boundary):** "No raw SQL that bypasses tenant-scoped session." The `@requires_tenant_scope` decorator encodes this at runtime; the fuzz harness (Story 1.10) verifies it at CI time.
- **§L820 (crypto):** pgcrypto for field-level crypto; AWS KMS deferred per AC13.

## Previous-story intelligence

- **Story 1.8** created all 8 canonical tables and one SQLAlchemy declarative `Base` + `target_metadata` wiring in `alembic/env.py`. The RLS migration in 1.9 is purely additive DDL on those tables — no model changes.
- **Story 1.8** installed `testcontainers[postgres]>=4.9.0` + `psycopg[binary]>=3.2.0` in control-plane's dev deps. No new Python deps for 1.9.
- **Story 1.8** established `# expand-contract: expand|contract` markers on migration `upgrade()` functions. `20260422_0002_*.py` follows the same convention.
- **Story 1.7**'s `pgvector/pgvector:pg16` image is what 1.8's testcontainers test uses. Stick with it for 1.9 so pgcrypto is already available (it's a bundled Postgres extension, not pgvector — but the 1.8 `conftest.py` already does `CREATE EXTENSION IF NOT EXISTS pgcrypto`).

## File map

Create:

```
services/_shared/tenancy/pyproject.toml
services/_shared/tenancy/src/deployai_tenancy/__init__.py
services/_shared/tenancy/src/deployai_tenancy/session.py
services/_shared/tenancy/src/deployai_tenancy/decorators.py
services/_shared/tenancy/src/deployai_tenancy/envelope.py
services/_shared/tenancy/src/deployai_tenancy/errors.py
services/_shared/tenancy/src/deployai_tenancy/py.typed
services/_shared/tenancy/tests/__init__.py
services/_shared/tenancy/tests/unit/__init__.py
services/_shared/tenancy/tests/unit/test_session.py
services/_shared/tenancy/tests/unit/test_decorators.py
services/_shared/tenancy/tests/unit/test_envelope.py
services/_shared/tenancy/tests/unit/test_errors.py
services/_shared/tenancy/README.md
services/control-plane/alembic/versions/20260422_0002_tenant_rls_policies.py
services/control-plane/src/control_plane/db.py
services/control-plane/tests/integration/test_tenant_isolation.py
docs/security/tenant-isolation.md
```

Modify:

```
services/control-plane/pyproject.toml        # [tool.uv.sources] + testpaths + dep
services/control-plane/uv.lock               # regenerate
docs/canonical-memory.md                      # update forward ref
docs/repo-layout.md                           # "Story 1.9 landed" entry
```

## Testing strategy

**Unit (runs under `pnpm turbo run test`, ~control-plane invocation covers both trees):**

- `services/_shared/tenancy/tests/unit/test_session.py` — AC2 cases.
- `services/_shared/tenancy/tests/unit/test_decorators.py` — AC3 cases.
- `services/_shared/tenancy/tests/unit/test_envelope.py` — `InMemoryDEKProvider` + helper shape tests.
- `services/_shared/tenancy/tests/unit/test_errors.py` — class hierarchy.

**Integration (runs under `schema.yml`, `-m integration`):**

- `test_tenant_isolation.py` — 6 cases per AC6 against a real Postgres container with pgcrypto + canonical-memory schema + new RLS migration applied.

## Risks

1. **`FORCE ROW LEVEL SECURITY` vs migration-runner role.** If the migration itself runs as the table owner and `FORCE` is enabled *before* the canonical tables have tenant_id populated (they don't yet, because 1.8 did not seed data), no data is lost. But for future migrations touching existing tenant data, the ALTER TABLE must temporarily drop FORCE or be run as `BYPASSRLS` role. Mitigated by documenting in `docs/security/tenant-isolation.md`.
2. **`SET LOCAL` transaction scope.** Works correctly with SQLAlchemy's async session (one transaction per session-lifetime by default). If a future story opens multiple transactions inside one session (e.g., via `session.begin_nested()`), the scope still holds — `SET LOCAL` is transaction-scoped, not savepoint-scoped. Unit-tested implicitly via AC2.
3. **uv workspace path dep on first-ever shared package.** Verified by running `uv sync` from `services/control-plane/` and confirming the `deployai-tenancy` package is importable. No packaging required (editable install).
4. **pgcrypto availability in `pgvector/pgvector:pg16` image.** pgcrypto is a bundled Postgres extension, always available — just needs `CREATE EXTENSION IF NOT EXISTS pgcrypto` (already in the Story 1.8 conftest).
5. **Naming conflict risk.** `app.current_tenant` is a GUC namespace Postgres uses for custom variables; no conflict with built-in `app.*` namespace.

## Out-of-scope deferrals (explicit)

See AC13. Re-stated:

- AWS KMS DEK provider → **Story 3.x**
- DEK rotation → **Story 12.x**
- Fuzz harness → **Story 1.10**
- `deployai_app` role as default connection user → **Story 2.4**
- Encrypted columns on canonical tables → **Epics 10, 11** (column-by-column as features need them)
- Cross-service tenant context propagation → **Story 2.4**

---

## Completion notes

Shipped on branch `feat/story-1-9-three-layer-tenant-isolation`:

- `services/_shared/tenancy/` — new `deployai-tenancy` package (editable path dep from control-plane). Exports `TenantScopedSession`, `@requires_tenant_scope`, `current_tenant()`, `DEKProvider`, `InMemoryDEKProvider`, `encrypt_field`, `decrypt_field`, full exception hierarchy.
- Alembic migration `20260422_0002_tenant_rls_policies.py` — 8 tables × `ENABLE + FORCE ROW LEVEL SECURITY + tenant_rls_<table>` policy; `deployai_app` role created `NOLOGIN NOINHERIT` (ops enables LOGIN at deploy time); `DROP POLICY IF EXISTS` before `CREATE POLICY` for idempotent re-runs.
- Adversarial code review (3 parallel reviewers: Blind Hunter, Edge Case Hunter, Acceptance Auditor) ran against the diff; patches applied:
  - `control_plane/db.py` default URL switched from `postgresql+asyncpg://` (driver missing) to `postgresql+psycopg://` (already in dep stack).
  - `pgp_sym_encrypt_bytea` now called with explicit `cipher-algo=aes256, s2k-mode=3, s2k-digest-algo=sha256, s2k-count=65011712` so the on-disk cipher matches what the docs claim.
  - `decrypt_field` raises `DEKUnavailable` on a NULL pgcrypto result instead of the opaque `TypeError: bytes(None)`.
  - `@requires_tenant_scope` validates *every* `AsyncSession` in args/kwargs (not just the first) and rejects async-generator functions at decoration time.
  - `_validate_tenant_id` rejects the nil UUID.
  - `InMemoryDEKProvider` rejects pepper < 16 bytes.
  - `current_tenant()` added to the `__init__.py` re-exports.
  - `tenant_id` / `is_tenant_scoped` also exposed as attributes on the session object (in addition to `session.info[...]`) for AC2 literal-text parity.
  - Integration test `test_cross_tenant_write_blocked` now asserts SQLSTATE `42501` rather than matching the English error string (locale-proof).
  - `test_scoped_session_sees_own_rows` extended to insert + verify reads across all 8 canonical tables (was only testing `canonical_memory_events`).
  - Docs: `docs/security/tenant-isolation.md` — FORCE RLS rationale corrected (defense-in-depth for future ownership transfers, not a hard block on the current superuser migration-runner).
- False-positive findings from review dismissed with reasoning (fixture already exists from Story 1.8; autouse TRUNCATE handles seed-row accumulation between tests).

Tests: 46 unit + 19 integration (8 new in `test_tenant_isolation.py` + 11 Story-1.8 schema tests) all green. `pnpm turbo run lint typecheck test build` → 20/20. `pnpm format:check` clean. `mypy strict` clean on both trees.

## Change log

- 2026-04-23: Story context authored (lean mode ~260 lines). Status: ready-for-dev.
- 2026-04-23: Implemented. Adversarial review applied. Ready for merge.
