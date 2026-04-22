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
| `packages/*` | Shared cross-workspace libraries: `design-tokens`, `citation-envelope`, `canonical-memory-primitives`, `llm-provider-abstraction`, `tenant-scope`, `shared-ui`, `event-contracts` | Authored directly |
| `infra/*` | Terraform + Terragrunt IaC (`infra/terraform/`), docker-compose reference dev env (`infra/compose/`), deferred Helm chart (`infra/helm/`) | Authored directly |
| `tests/*` | Cross-workspace test harnesses: `11th-call/`, `continuity-of-reference/`, `phase-retrieval-matrix/`, `tenant-isolation-fuzz/`, `e2e-user-journeys/` | Authored directly |

> **Status (post-Story-1.1):** Every workspace root exists as an empty directory (with `.gitkeep`). No workspaces have been initialized. Story 1.3 initializes `apps/*` and the first `services/*` project; Story 1.4 creates `packages/design-tokens/`; Story 1.7 lands `infra/compose/`; Story 1.10 lands `tests/tenant-isolation-fuzz/`; and so on.

## Root-level configuration

| File | Purpose |
|---|---|
| `package.json` | Workspace root (`private: true`) — pins `turbo`, `typescript`, `eslint`, `prettier`, `@eslint/js`, `globals`, `@types/node` as dev deps. Declares canonical scripts. `packageManager` pins pnpm via Corepack. |
| `pnpm-workspace.yaml` | Workspace globs (the five roots above). |
| `pnpm-lock.yaml` | Lockfile (always committed). |
| `turbo.json` | Pipeline topology: `build`, `lint`, `test`, `typecheck`, `dev`, `clean`. |
| `tsconfig.base.json` | Shared strict TypeScript compiler settings. Each TS workspace extends this. |
| `eslint.config.mjs` | ESLint **flat config** (ESLint 10+ default; no legacy `.eslintrc*`). |
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

## What this repo does NOT yet contain (by design, as of Story 1.1)

- No framework projects (`apps/web`, `apps/edge-agent`, `apps/foia-cli`, any `services/*`) — deferred to Story 1.3.
- No CI workflows (`.github/workflows/`) — deferred to Story 1.2 (baseline CI + SLSA L2 + Cosign + Syft SBOM + Grype).
- No design system (`packages/design-tokens/`) — deferred to Story 1.4.
- No shadcn/ui init — deferred to Story 1.5.
- No accessibility gate stack — deferred to Story 1.6.
- No docker-compose dev env — deferred to Story 1.7.
- No Alembic migrations or canonical-memory schema — deferred to Story 1.8.
- No pre-commit hooks — deferred to Story 1.3 (land alongside first TypeScript code).

Each future story adds exactly its deliverable; Story 1.1 establishes only the foundation on which they build.
