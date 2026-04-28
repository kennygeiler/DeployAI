# DeployAI — Repository Layout

This document is the canonical reference for how the DeployAI monorepo is organized, which workspace each future piece of code belongs to, and how to add new workspaces cleanly.

**Runtime baseline:** Node.js 24 LTS · pnpm 10.33.0 · TypeScript 6.0 · Turborepo 2.9. See `.nvmrc` and `.tool-versions` for exact pins. Enforcement is real: the root `.npmrc` sets `engine-strict=true`, which means pnpm hard-fails (not merely warns) any command when Node or pnpm is outside the `engines` range declared in `package.json`.

## Workspaces

The root `pnpm-workspace.yaml` declares five workspace roots. Every future top-level directory a story creates must live under one of these.

| Path | Purpose | Starter command (Story 1.3) |
|---|---|---|
| `apps/web` | Next.js 16 App Router web app (React 19, Tailwind v4, shadcn/ui) | `pnpm create next-app@latest . --typescript --tailwind --eslint --app --src-dir --turbo` |
| `apps/edge-agent` | Tauri 2.x desktop edge-capture agent (macOS V1 per FR13, FR14, NFR20) | `pnpm create tauri-app@latest . --template react-ts` |
| `apps/foia-cli` | Go FOIA verification CLI — single static binary, Sigstore-signed (FR60, FR61) | `go mod init github.com/kennygeiler/deployai/foia-cli` |
| `services/*` | FastAPI + Pydantic v2 + SQLAlchemy 2.x async Python services (`api-gateway`, `canonical-memory`, `ingest`, `cartographer`, `oracle`, `master-strategist`, `control-plane`, `foia-export`, `replay-parity-harness`). Authored from reference patterns, not a single generator. | `uv init` per service |
| `packages/*` | Shared cross-workspace libraries: `design-tokens`, `contracts` (citation envelope v0.1+), `llm-provider` (1.14), `shared-ui` (Epic 7) | Authored directly |
| `infra/*` | Terraform + Terragrunt IaC (`infra/terraform/`), docker-compose reference dev env (`infra/compose/`), deferred Helm chart (`infra/helm/`) | Authored directly |
| `tests/*` | Cross-workspace test harnesses: `11th-call/`, `continuity-of-reference/`, `phase-retrieval-matrix/`, `tenant-isolation-fuzz/`, `e2e-user-journeys/` | Authored directly |

> **Current scope (2026-04):** The monorepo is populated across **`apps/*`**, multiple **`services/*`** (control-plane, ingest, cartographer, oracle, master_strategist, …), **`packages/*`** (design-tokens, contracts, shared-ui, authz, …), **`infra/compose`**, and **`tests/**`. Epic/story completion is tracked in [**`_bmad-output/implementation-artifacts/sprint-status.yaml`**](../_bmad-output/implementation-artifacts/sprint-status.yaml); **fixture vs live APIs** for strategists is summarized in [**`whats-actually-here.md`**](../whats-actually-here.md). The row below labeled **Story 1.3 shipped** is a historical snapshot of first bootstrap — not an exhaustive list of today’s modules.

## Root-level configuration

| File | Purpose |
|---|---|
| `package.json` | Workspace root (`private: true`) — pins `turbo`, `typescript`, `eslint`, `prettier`, `@eslint/js`, `globals`, `@types/node` as dev deps. Declares canonical scripts. `packageManager` pins pnpm via Corepack. |
| `pnpm-workspace.yaml` | Workspace globs (the five roots above). |
| `pnpm-lock.yaml` | Lockfile (always committed). |
| `turbo.json` | Pipeline topology: `build`, `lint`, `test`, `typecheck`, `dev`, `clean`. |
| `tsconfig.base.json` | Shared strict TypeScript compiler settings. Each TS workspace extends this. |
| `eslint.config.mjs` | ESLint **flat config** (ESLint **9.x** in-repo for Next.js ecosystem compat; no legacy `.eslintrc*`). |
| `.prettierrc.json` / `.prettierignore` | Prettier rules + ignores. |
| `.editorconfig` | Editor-level consistency (UTF-8, LF, 2-space default, 4-space Python, tab Go). |
| `.npmrc` | pnpm config — turns on `engine-strict=true` (hard-fails non-conforming Node/pnpm) and `frozen-lockfile=true`. |
| `.nvmrc` | Node major LTS pin (`24`). |
| `.tool-versions` | asdf-compatible Node + pnpm pinning (`nodejs 24.15.0`, `pnpm 10.33.0`). |
| `.env.example` | Template for `.env`. Hashed by Turborepo via `globalDependencies` to keep build cache keys deterministic across contributors even though `.env` itself is gitignored. |
| `.github/CODEOWNERS` | Ownership routing (currently `* @kennygeiler`). |
| `.gitignore` | Stack-wide ignores for Node/Python/Go/Rust/Tauri/Terraform/Docker/OS/IDE/secrets. |

## Root scripts

All workspace-aware scripts delegate to `turbo`:

| Script | Runs | Purpose |
|---|---|---|
| `pnpm build` | `turbo run build` | Compile every workspace. |
| `pnpm lint` | `turbo run lint` | ESLint + language-specific linters per workspace. |
| `pnpm test` | `turbo run test` | Unit + integration tests per workspace (dependsOn build). |
| `pnpm typecheck` | `turbo run typecheck` | `tsc --noEmit` per TS workspace (dependsOn ^build). |
| `pnpm dev` | `turbo run dev` | Persistent, non-cached dev servers across workspaces. |
| `pnpm format` | `prettier --write .` | Format-in-place across the repo. |
| `pnpm format:check` | `prettier --check .` | CI-friendly format verification. |
| `pnpm clean` | `turbo run clean && rm -rf node_modules .turbo` | Full reset. |

## Adding a new workspace

1. **Pick the right root.** User-facing deployables → `apps/`. Backend deployables → `services/`. Reusable libraries → `packages/`. Infra-as-code → `infra/`. Cross-workspace test harnesses → `tests/`.
2. **Create the directory** under the chosen root, e.g., `packages/citation-envelope/`.
3. **Author the manifest** appropriate to the language. Only `package.json`-bearing workspaces are discovered by pnpm and orchestrated by Turborepo; Python/Rust/Go workspaces are co-located (for tooling, docs, and cross-workspace tests) but managed by their own tools:
   - **TypeScript/JavaScript** — `package.json` with `name`, `version`, and `build` / `lint` / `test` / `typecheck` scripts. pnpm discovers via the workspace glob; Turbo orchestrates via the root task graph.
   - **Python** — `pyproject.toml` managed by `uv` (locks `uv.lock`). Add a `Dockerfile` per `services/` convention. pnpm will **not** pick it up; add a sibling `package.json` only if you want the workspace in the turbo graph as a thin wrapper around `uv run …`.
   - **Rust** — `Cargo.toml` (Tauri workspaces live at `apps/edge-agent/src-tauri/`). Managed by `cargo`; Turbo integration is via a `package.json` wrapper calling `cargo build`.
   - **Go** — `go.mod` rooted at a stable module path. Managed by `go`; same wrapper pattern for Turbo integration.
4. **Extend shared configs** where applicable:
   - **TypeScript** — `extends` from `../../tsconfig.base.json`. **Critical overrides you almost always need:**
     - For **library workspaces that emit `.d.ts`** (most `packages/*`): set `"noEmit": false` and `"outDir": "./dist"`. The base sets `noEmit: true`, which silently suppresses `declaration: true` + `sourceMap: true` emission — so forgetting this override means the library produces no artifacts with no error.
     - For **browser/bundler workspaces** (`apps/web` Next.js, `apps/edge-agent` Tauri frontend): override `"module": "bundler"` and `"moduleResolution": "bundler"`. The base's `"nodenext"` setting requires `.js` extensions on relative imports and targets Node runtime semantics — it will not work for Next.js or any Vite/Rollup/esbuild-bundled target.
   - **ESLint** — if the workspace has TS/JSX, attach the appropriate ESLint plugins in its own `eslint.config.mjs`. The root config only wires plain JS + Node globals; browser workspaces must add `globals.browser` in their own config (Story 1.3 establishes the per-workspace pattern).
5. **Run `pnpm install` from the repo root.** If the new workspace has a `package.json`, pnpm discovers it via the workspace glob and hydrates `node_modules`. If it's Python/Rust/Go-only, `pnpm install` is a no-op for that workspace — run `uv sync` / `cargo fetch` / `go mod download` in the workspace directory instead.
6. **Verify the task graph picks it up:** `pnpm turbo run build --filter=<workspace-name>` and `pnpm turbo run lint --filter=<workspace-name>`.

## Filename conventions

- **TypeScript/JavaScript:** `kebab-case.ts`, `kebab-case.tsx`. One component per file. Type exports use `PascalCase`; identifier names use `camelCase`; constants `UPPER_SNAKE`.
- **Python:** `snake_case.py`. Classes `PascalCase`; functions + vars `snake_case`; constants `UPPER_SNAKE`.
- **Rust:** module `snake_case`, types `PascalCase`.
- **Go:** file `snake_case.go`, exports `MixedCaps`.

Source: architecture.md §Code Naming.

## Runtime manager notes

- **Node version**: pinned via `.nvmrc` (`24`) and `.tool-versions` (`nodejs 24`). Use `nvm use`, `fnm use`, or `asdf install` to align.
- **pnpm version**: driven by Corepack. Enable once: `corepack enable`. Subsequent `pnpm` commands resolve from `packageManager` in `package.json`, so every contributor runs the exact same pnpm version.
- **Do not** install pnpm globally via Homebrew/npm if you can avoid it — Corepack will shadow any global pnpm on PATH in most shells, but version drift can still cause surprises during debugging.

## What Story 1.3 shipped

| Workspace | Stack | Entry point | Wrapper scripts |
|---|---|---|---|
| `apps/web` | Next.js 16.2 + React 19.2 + Tailwind v4 + Turbopack + Vitest | `src/app/page.tsx` ("DeployAI — initializing") | `dev`, `build`, `start`, `lint`, `typecheck`, `test`, `docker:build` |
| `apps/edge-agent` | Tauri 2.10 + Rust 1.95 + React 19 + capability sets per [`docs/edge-agent/capabilities.md`](./edge-agent/capabilities.md) | `src-tauri/src/lib.rs` (edge commands; updater/signing/transcript/kill-switch modules) | `dev` (**`tauri dev`** + Vite **:1420** via **`vite:dev`**), `vite:dev`, `build`, `tauri`, `cargo:check`, `lint`, `typecheck`, `test`, `docker:build` |
| `apps/foia-cli` | Go 1.26 + static `CGO_ENABLED=0` binary, stripped (`-s -w`) | `cmd/foia/main.go` prints version + `verify.Description()` | `build`, `lint` (gofmt + go vet), `test`, `typecheck`, `docker:build` |
| `services/control-plane` | FastAPI 0.136 + Pydantic v2 + SQLAlchemy 2.x async + Alembic (empty async template) + uv 0.11 | `src/control_plane/main.py` with `GET /healthz` → `{"status": "ok"}` | `dev`, `build` (uv sync), `lint` (ruff + ruff format), `typecheck` (mypy strict), `test` (pytest-asyncio), `docker:build` |

Additional root-level artifacts landed:
- `rust-toolchain.toml` (Rust 1.95.0 + rustfmt + clippy), `.python-version` (3.13), `go.work` (single-module workspace).
- `.pre-commit-config.yaml` — prettier, ruff (and ruff-format) on staged Python in control-plane, ingest, cartographer, oracle, and master_strategist; gofmt, go vet, cargo fmt on staged files.
- `docs/dev-environment.md` — 5-minute bootstrap for the full polyglot stack.
- `turbo.json` gains a `docker:build` task type.

Everything the CI smoke gate already enforces (`install → turbo build/lint/typecheck/test → prettier --check`) continues to pass on the 5-job CI pipeline introduced in Story 1.2.

## What Story 1.4 shipped

| Workspace | Stack | Entry point | Wrapper scripts |
|---|---|---|---|
| `packages/design-tokens` | Pure-TS token source + `wcag-contrast` AA tests, emits `dist/tokens.css` (raw vars) + `dist/tailwind.css` (Tailwind v4 `@theme` preset) | `src/index.ts` re-exports `colors`, `spacing`, `typography`, `shadows`, `radii`, `elevation`, `motion`. UX-DR1 + UX-DR2. | `build` (tsc + tsx CSS emitter), `lint`, `typecheck`, `test`, `clean` |

Additional changes:

- `apps/web` consumes `@deployai/design-tokens` via `workspace:*`; `src/app/globals.css` `@import`s both the Tailwind preset and the raw CSS bundle; `src/app/layout.tsx` loads Inter + IBM Plex Mono through `next/font/google` and exposes them as the `--font-inter` / `--font-mono` CSS variables the tokens consume. No hardcoded colors / spacing / fonts remain anywhere in `apps/web/src/`.
- **Storybook 10** (`@storybook/nextjs-vite` — first major to support Next.js 16) initialized in `apps/web` with `@storybook/addon-a11y` + `@storybook/addon-docs`. Scripts: `pnpm storybook` (dev on `:6006`), `pnpm build-storybook` (static build to `storybook-static/`, already declared as a `build` output in `turbo.json`).
- `apps/web/src/stories/Foundations/Tokens.stories.tsx` renders the palette, type ramp, spacing ladder, and radii + shadows library — the surface for design review and drift detection.
- `docs/design-tokens.md` documents the palette rationale (no primary green), the 4 px spacing ladder, the Inter + IBM Plex Mono type ramp, the WCAG AA contrast methodology, the shadcn bridge plan for Story 1.5, and the "add a new token" checklist.
- `@deployai/design-tokens` is the canonical **library workspace** shape — future `packages/*` clone its `tsconfig.build.json` pattern (`noEmit: false`, `declaration: true`, `outDir: ./dist`).

## What Story 1.5 shipped

| Workspace | Addition | Primary files | Notes |
|---|---|---|---|
| `apps/web` | shadcn/ui initialized with the 23-primitive core set and theme-bridged to `@deployai/design-tokens` | `apps/web/components.json`, `apps/web/src/components/ui/*.tsx` (23 files), `apps/web/src/lib/utils.ts`, `apps/web/src/app/globals.css` (`@layer base :root` + `@theme inline`) | No dark-mode block, no `<Toaster />` mount, no `packages/shared-ui/` (deferred to Epic 7). See [shadcn.md](./shadcn.md) for the full contract. |
| `apps/web` | Reference form component + test suite | `apps/web/src/components/forms/ExampleForm.tsx`, `apps/web/src/components/forms/ExampleForm.test.tsx` | Canonical `react-hook-form` + `zod` + shadcn `<Form>` composition; exercises on-blur format + on-submit completeness + Cmd+Enter submit. |
| `apps/web` | `Foundations/ButtonVariants` Storybook surface | `apps/web/src/stories/Foundations/ButtonVariants.stories.tsx` | Renders every variant × size × state combination required by UX-DR39; clean under `@storybook/addon-a11y` (wcag2a + wcag2aa + wcag21aa + wcag22aa). |

Additional changes:

- `apps/web/eslint.config.mjs` and root `.prettierignore` both ignore `apps/web/src/components/ui/**` so shadcn-authored files stay diff-clean through future `shadcn add` regenerations (treated as vendored third-party code).
- `apps/web/tsconfig.json` scopes `exactOptionalPropertyTypes: false` (the rest of the monorepo keeps the strict flag from `tsconfig.base.json`) — shadcn + Radix optional-prop surfaces type `prop?: T` rather than `prop?: T | undefined`, which the strict flag rejects.
- Runtime deps gained in `apps/web`: `@hookform/resolvers`, `class-variance-authority`, `clsx`, `cmdk`, `lucide-react`, `next-themes` (Sonner peer), `radix-ui` (shadcn v4 unified surface), `react-hook-form`, `sonner`, `tailwind-merge`, `tw-animate-css`, `zod`. Dev deps gained: `@testing-library/user-event`.
- `docs/shadcn.md` (new) documents the theme-bridge pattern, `components.json` field-by-field, the form stack, anti-patterns, and "how to add a primitive" recipe.
- `docs/design-tokens.md`'s shadcn-bridge section is updated in place with the real CSS that shipped.

## What Story 1.6 shipped

| Workspace / Path | Addition | Primary files |
|---|---|---|
| `apps/web` | `eslint-plugin-jsx-a11y` at `error` severity (all 34 recommended rules) | `apps/web/eslint.config.mjs` |
| `apps/web` | Shared a11y config module (single source of truth for axe WCAG tag list + disabled-rules ledger) | `apps/web/src/lib/a11y-config.ts` |
| `apps/web` | `@axe-core/react` dev runtime (tree-shaken from prod) | `apps/web/src/lib/axe.ts`, `apps/web/src/app/axe-dev.tsx`, `apps/web/src/app/layout.tsx` |
| `apps/web` | Skip-to-main-content link (WCAG 2.4.1) | `apps/web/src/app/layout.tsx` |
| `apps/web` | `@storybook/test-runner` CI gate with `@axe-core/playwright` `postVisit` hook | `apps/web/.storybook/test-runner.ts` |
| `apps/web` | Playwright E2E + axe baseline + gate-proof fixture | `apps/web/playwright.config.ts`, `apps/web/tests/e2e/homepage.a11y.spec.ts`, `apps/web/tests/e2e/gate-catches-violation.spec.ts`, `apps/web/tests/e2e/fixtures/violating-page.html` |
| `apps/web` | `pa11y-ci` config with dual `axe` + `htmlcs` runners | `apps/web/.pa11yci.json` |
| `.github/workflows` | 4-job a11y workflow (`jsx-a11y`, `storybook-a11y`, `playwright-a11y`, `pa11y`) | `.github/workflows/a11y.yml` |
| `docs/` | Full a11y-gates reference: runner coverage, WCAG tag policy, axe version alignment, appeal process, on-call | `docs/a11y-gates.md` |

Additional changes:

- `turbo.json` gains `test:e2e` and `test:a11y` task definitions; root `package.json` gains `test:e2e` and `test:a11y` convenience scripts.
- `.gitignore` gains entries for `playwright-report/`, `test-results/`, and `pa11y-screenshots/`.
- `apps/web/src/components/forms/ExampleForm.tsx` carries one jsx-a11y appeal (inline `eslint-disable` for `<form onKeyDown>` Cmd/Ctrl+Enter shortcut) with rationale + doc pointer, per the appeal process in `docs/a11y-gates.md`.

## What Story 1.7 shipped

| Path | Addition | Primary files |
|---|---|---|
| `infra/compose/` | Reference local-dev stack: Postgres 16 (pgvector + pgcrypto), Redis 7, MinIO, FreeTSA stub, control-plane, web — bootable via `make dev` in ≤ 30 min | `infra/compose/docker-compose.yml`, `infra/compose/.env.example`, `infra/compose/postgres/Dockerfile`, `infra/compose/postgres/init/01-extensions.sql`, `infra/compose/freetsa-stub/Dockerfile`, `infra/compose/freetsa-stub/default.conf` |
| `infra/compose/seed/` | Idempotent seeder for `fixtures.*` schema (1 synthetic tenant, ≥ 6 stakeholders, ≥ 20 canonical events, 1 sample phase row) | `infra/compose/seed/schema.sql`, `infra/compose/seed/seed.sh` |
| repo root | `make dev` / `make dev-verify` / `make dev-down` / `make dev-logs` / `make compose-smoke` targets | `Makefile` |
| `.github/workflows` | 30-min-ceiling CI smoke gate for the local stack | `.github/workflows/compose-smoke.yml` |
| `services/control-plane` | `GET /health` alias of `/healthz` (satisfies AC4 literal path) | `services/control-plane/src/control_plane/main.py`, `services/control-plane/tests/unit/test_healthz.py` |
| `apps/web` | `/admin/runs` stub route (Story 1.16 ships the real shell); Dockerfile fixed to copy `packages/design-tokens/` so Next build resolves `@deployai/design-tokens/tailwind` | `apps/web/src/app/admin/runs/page.tsx`, `apps/web/Dockerfile` |
| `docs/` | §"Local stack via docker-compose" added to `dev-environment.md` | `docs/dev-environment.md` |

## What Story 1.8 shipped

| Path | Addition | Primary files |
|---|---|---|
| `services/control-plane/alembic/versions/` | Initial canonical-memory migration: 8 tables in `public`, `deployai_uuid_v7()` plpgsql function, append-only trigger on `canonical_memory_events`, `learning_state_t` enum | `services/control-plane/alembic/versions/20260422_0001_canonical_memory_schema.py` |
| `services/control-plane/src/control_plane/domain/` | SQLAlchemy 2.x async declarative models for every canonical-memory table; shared `Base` with naming conventions | `services/control-plane/src/control_plane/domain/base.py`, `services/control-plane/src/control_plane/domain/canonical_memory/*.py` |
| `services/control-plane/alembic/env.py` | `target_metadata = Base.metadata`; dispatches async vs sync based on URL driver so the integration-test harness can feed a psycopg URL | `services/control-plane/alembic/env.py` |
| `services/control-plane/tests/unit/` | Expand-contract migration guardrail (NFR74) — scans `alembic/versions/` and requires a `# expand-contract:` marker on any `ALTER COLUMN` touching a canonical-memory table | `services/control-plane/tests/unit/test_migration_guardrails.py` |
| `services/control-plane/tests/integration/` | testcontainers[postgres]-driven integration suite (append-only trigger, UUID v7 ordering, partial-unique attribute history, supersession CHECK, enum rejection, lifecycle transitions, tombstone bytea) | `services/control-plane/tests/integration/conftest.py`, `services/control-plane/tests/integration/test_canonical_memory_schema.py` |
| `.github/workflows/` | Path-filtered `schema.yml` CI job runs the integration suite on a fresh `pgvector/pgvector:pg16` testcontainer | `.github/workflows/schema.yml` |
| `docs/` | `docs/canonical-memory.md` — schema inventory, append-only contract, UUID v7 rationale, expand-contract convention, forward references to 1.9/1.13/1.17 | `docs/canonical-memory.md` |

Seed fixtures (Story 1.7) still live in the separate `fixtures.*` schema — Story 1.8's canonical memory lands in `public.*` so both coexist without conflict.

## What Story 1.9 shipped

| Path | Addition | Primary files |
|---|---|---|
| `services/_shared/tenancy/` | New `deployai-tenancy` uv workspace package — `TenantScopedSession`, `@requires_tenant_scope`, `DEKProvider`/`InMemoryDEKProvider`, `encrypt_field`/`decrypt_field`, error hierarchy, full unit suite | `services/_shared/tenancy/src/deployai_tenancy/*.py`, `services/_shared/tenancy/tests/unit/*.py` |
| `services/control-plane/alembic/versions/` | RLS expand migration: `tenant_rls_<table>` on all 8 canonical tables, `FORCE ROW LEVEL SECURITY`, `deployai_app` role with grants | `services/control-plane/alembic/versions/20260422_0002_tenant_rls_policies.py` |
| `services/control-plane/src/control_plane/db.py` | Cached async engine + `tenant_session(tenant_id)` convenience wrapper | `services/control-plane/src/control_plane/db.py` |
| `services/control-plane/tests/integration/` | Three-layer isolation integration tests: scoped reads/writes, cross-tenant block, fail-closed raw session, envelope round-trip, FORCE-RLS proof on `deployai_app`, concurrent-scope context-var isolation | `services/control-plane/tests/integration/test_tenant_isolation.py` |
| `services/control-plane/pyproject.toml` | `deployai-tenancy` editable path dep, `[tool.uv.sources]`, `aiosqlite` dev dep, importlib mode for tests (resolves tenancy ↔ control-plane `tests.unit.*` namespace clash) | `services/control-plane/pyproject.toml` |
| `docs/` | `docs/security/tenant-isolation.md` (new) — three-layer defense walkthrough, BYPASSRLS gotcha, fail-closed semantics, scope fences (KMS, rotation, role swap). `docs/canonical-memory.md` updated to reference 1.9 migration + tenancy package. | `docs/security/tenant-isolation.md`, `docs/canonical-memory.md` |

## What Story 1.10 shipped

| Path | Addition | Primary files |
|---|---|---|
| `services/control-plane/src/control_plane/fuzz/` | Cross-tenant RLS/SQLi/`SET ROLE` harness + JSON report; CLI `python -m control_plane.fuzz.cross_tenant` | `cross_tenant.py`, `attacks.py`, `report.py` |
| `services/control-plane/tests/fuzz/` | Meta-tests, production-gated pytest run, anti-test for disabled-RLS detection | `test_cross_tenant_harness.py`, `test_cli_production_run.py` |
| `.github/workflows/` | Path-filtered `fuzz.yml` (**required** on `main` when the workflow runs; see `.github/workflows/README.md` §3) | `.github/workflows/fuzz.yml` |
| `docs/security/` | Operator-facing triage for the harness | `docs/security/cross-tenant-fuzz.md` |
| `turbo.json` / `package.json` | `fuzz:cross-tenant` task + pnpm script with `--seed` | `services/control-plane/package.json`, `turbo.json` |

## What Story 1.11 shipped

| Path | Addition | Primary files |
|---|---|---|
| `packages/contracts` | `@deployai/contracts` — Zod citation envelope v0.1.0, Vitest contract tests, committed JSON Schema, `contract:check` (CI) | `src/citation-envelope.ts`, `schema/citation-envelope-0.1.0.schema.json` |
| `migrations/contracts/` | Human-readable breaking-change policy for future semver bumps | `migrations/contracts/README.md` |
| `services/_shared/citation` | `deployai-citation` Pydantic mirror (path dep of control-plane) | `src/deployai_citation/citation.py` |
| `docs/contracts/` | Field semantics (FR27) | `docs/contracts/citation-envelope.md` |
| `.github/workflows/ci.yml` | `pnpm turbo run contract:check` on the main smoke job | `ci.yml` (smoke job) |

## Rolling gaps and deferred systems

The old **“Story 1.11 gap list”** has been **removed** — it falsely claimed `services/*` beyond control-plane, missing `shared-ui`, missing FOIA CLI, missing edge signing, etc., all of which **exist on `main`** now.

**Authoritative tracking:** [sprint-status.yaml](../_bmad-output/implementation-artifacts/sprint-status.yaml) · **Honest UX/API posture:** [whats-actually-here.md](../whats-actually-here.md) · **Deferred follow-ups:** [deferred-work.md](../_bmad-output/implementation-artifacts/deferred-work.md).

Examples that remain **open or partial** at the platform level (not exhaustive): **Epic 12** compliance/operability stories (SLOs, chaos, immutable audit bucket, …), **Epic 13** usability/VPAT program, **full Grafana-style observability stack** in compose (see Epic **12.10**), **AWS-KMS DEK** vs dev providers where not yet wired, **screen-reader automation** for releases, **mobile viewport** tooling depth vs desktop-first gates.
