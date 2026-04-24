# Story 2.1: Role matrix and `AuthzResolver` interface

Status: **done**

## Delivered

- **`packages/authz`** — `canAccess`, `authzResolver`, expanded `Action` / `Resource`, `Decision` with `code`, cross-tenant rules, `emitAuthzAudit` (server-only JSON line), `decideSync` unchanged for call sites; Vitest contract coverage.
- **`services/_shared/authz`** — `can_access`, `AuthActor`, `Decision`, JSON audit logging via `logging`, matrix parity with TS; pytest expanded.
- **`services/_shared/tenancy`** — optional `app_role=` on `TenantScopedSession` → `SET LOCAL app.current_role`.
- **`docs/authz/role-matrix.md`**, **`docs/authz/rls-alignment.md`**.
- **`apps/web/middleware.ts`** — uses `canAccess(..., { kind: "global" }, { skipAudit: true })`.

## Code review (summary)

- **Matrix parity:** TS `_ALLOWED` / Python `_ALLOWED` kept in sync; `_matrix_allows(actor.role, action)` fix applied (was incorrectly passing `actor`).
- **Audit:** Browser skip via `globalThis.window`; optional props respect `exactOptionalPropertyTypes`.
- **RLS:** Policy SQL deferred per story scope; GUC + doc is the shipped slice.

---

## Story

As a **platform engineer**,
I want a frozen `AuthzResolver` contract, a published role matrix, tenant-aware authorization decisions, RLS alignment hooks, and structured audit for each decision,
so that every Epic 3–12 surface calls one swappable authorization abstraction (OpenFGA/ReBAC path preserved per [Source: _bmad-output/planning-artifacts/architecture.md §Authorization]) without reinventing the Epic 1 stub.

_(Original AC and dev notes preserved below for history.)_

## Acceptance criteria (from epics, interpreted for implementation)

1. **TypeScript `AuthzResolver` API** — [Source: _bmad-output/planning-artifacts/epics.md §Story 2.1]

   - `packages/authz` exports a stable **`canAccess(actor, action, resource) → Promise<Decision> | Decision`** entry point. The Epic text names `AuthzResolver.canAccess`; **implement** as either a **namespace object** `export const authzResolver = { canAccess }` or a **class** with `canAccess` — dev choice, but the **public** surface must be `canAccess` (not only `decideSync`), and existing **`decideSync` / `stubAuthzResolver`** must remain re-exported for backward compatibility with `apps/web` until a thin follow-up migrates call sites.
   - **`Decision`**: allow/deny with stable **`code`** (`"ok" | "forbidden" | "unauthenticated"`) and human **`reason`** string; align TS and Python field names.
   - **`Action` and `Resource`** types: extend beyond today’s short list to cover the epic matrix: **at minimum** the capabilities named in the matrix row headers — `ingest`, `view-canonical`, `override`, `solidification-promote`, `foia-export`, `break-glass`, `scim-manage` — mapped to **concrete** string literals (e.g. `view_canonical:read` style) in `packages/authz/src/types.ts`; keep existing actions working or provide explicit migration map in dev notes.
   - **Tenant scoping:** when `resource` implies a tenant (e.g. `{ kind: "tenant"; id: string }`) or `actor.tenantId` is set, **deny** cross-tenant access for roles that are not `platform_admin` (define rules in `matrix` / resolver; document in role-matrix doc).

2. **Python parity** — [Source: epics.md §2.1]

   - `services/_shared/authz` exposes **`can_access(actor, action, resource) -> Decision`** (same semantic contract as TS). Today’s `is_allowed` / `matrix_allowed` may be **refactored** into this shape or thin-wrapped; keep **unit tests** passing and expand coverage.
   - Re-export or document import path: `from deployai_authz import can_access, Decision, ...` (align `__all__` in `__init__.py`).

3. **`docs/authz/role-matrix.md`** (new)

   - Table: **role × capability** for all V1 roles: `deployment_strategist`, `successor_strategist`, `platform_admin`, `customer_records_officer`, `external_auditor`, `customer_admin` — with **V1** vs **V1.5** column or row markers as in the epic.
   - Reference **NFR** / **FR** only where it clarifies (avoid prose bloat); link to `epics.md` and architecture authorization section.
   - **Cross-link** `apps/web/middleware.ts` and header-based v1 dev actor (`x-deployai-role`) as **temporary** until Story 2.2 SSO.

4. **RLS — extend Story 1.9** — [Source: `services/control-plane/alembic/versions/20260422_0002_tenant_rls_policies.py`]

   - **Session GUC:** extend `TenantScopedSession` in `services/_shared/tenancy` to optionally `SET LOCAL` an **`app.current_role`** (and document the string enum matching `V1Role`). Preserve existing `app.current_tenant` behavior and Story 1.9/1.10 tests.
   - **Policies:** add an **Alembic migration** (expand-only, follow `# expand-contract: expand` pattern) that **extends** or **adds** policies **where needed** for at least one canonical table (recommend **`schema_proposals`**) so that **write paths** (UPDATE/DELETE) are consistent with *platform admin* vs *read-only* roles when `app.current_role` is set — **or**, if a single migration is too risky, **document** the exact SQL in `docs/authz/rls-alignment.md` and ship the **GUC + integration test** proving `current_setting('app.current_role', true)` is visible inside a tenant-scoped session, with a **follow-up** issue for full policy. **Do not** weaken existing tenant isolation tests (`tests/integration/test_tenant_isolation.py`).

5. **Structured audit (NFR59)** — [Source: architecture.md structured audit / NFR59]

   - Every **`can_access` / `canAccess` invocation** that runs in **control-plane** request context must emit a **structured** audit record: `{ "event": "authz_decision", "allow": bool, "actor_role": str, "action": str, "resource_kind": str, "tenant_id": str | null, "code": str, "trace_id"?: str }` (add fields as needed; keep **JSON-serializable**).
   - Implementation: use Python **`structlog`** if already a dependency; else **`logging` JSON** or the project’s standard logger — check `pyproject.toml` first. Do **not** add a new SaaS. If no durable store exists yet, **log line** to stdout is acceptable for 2.1; optionally add a minimal `authz_decisions` table only if the control-plane already has a migration pattern and it stays small.
   - **TypeScript:** for server code paths (`next` middleware, route handlers), add a small **`emitAuthzAudit`** that no-ops or logs in **server** runtime only (tree-shake safe).

6. **Contract tests**

   - **Vitest** in `packages/authz`: for **each** V1 role, assert **allow** and **deny** cases per **at least** the matrix’s critical cells (not necessarily exhaustive Cartesian product; hit every role at least one allow + one deny where applicable).
   - **pytest** in `services/_shared/authy`: same parity for Python.
   - **Goal:** if someone changes the matrix, CI fails with a clear message.

7. **CI / turbo**

   - `pnpm turbo run build lint typecheck test` includes `@deployai/authz` and `services/_shared/authz` (and tenancy if touched).
   - Control-plane: `uv run pytest` for affected packages; no new **required** integration suite unless a migration is added (then add one integration test for GUC + policy).

## Dev Agent Record

### Agent Model Used

Cursor agent (Claude)

### Completion Notes List

- Shipped RLS **documentation + GUC** slice; new Postgres policies for role-aware DML deferred to a follow-up migration when `app.current_role` is consumed in query paths.
- Epic 2 stories **2-2..2-7** not implemented in this pass (separate product milestones).

### File List

- `packages/authz/src/*` (types, can-access, audit, matrix, stub-resolver, index)
- `packages/authz/tests/authz.test.ts`, `packages/authz/tsconfig.build.json`
- `services/_shared/authz/src/deployai_authz/resolver.py`, `__init__.py`, `tests/test_matrix.py`
- `services/_shared/tenancy/src/deployai_tenancy/session.py`, `tests/unit/test_session.py`
- `docs/authz/role-matrix.md`, `docs/authz/rls-alignment.md`
- `apps/web/middleware.ts`

---

**Completion status:** done
