# DeployAI Dev Environment Bootstrap (5-minute setup)

Story 1.3 lands the full polyglot stack. Running any workspace locally now requires Node.js + pnpm, Rust, Go, Python, and a handful of small helpers.

## 1. Install the runtimes

Pin versions match the repo files (`.tool-versions`, `rust-toolchain.toml`, `.python-version`, `apps/foia-cli/go.mod`). Homebrew is the sanctioned macOS path; Linux users can swap in `apt`, `asdf`, `rustup`, etc.

```bash
# Node 24 + pnpm 10 (if not already done in Story 1.1)
# Root `package.json` enforces `engines.node`: `>=24.0.0 <25.0.0` (see `.nvmrc`).
# Use Node 24.x for `pnpm install`, `pnpm turbo`, and workspace scripts — pnpm
# will refuse a mismatch (e.g. Node 25) with `ERR_PNPM_UNSUPPORTED_ENGINE`.
brew install node@24
corepack enable && corepack prepare pnpm@10.33.0 --activate

# Python 3.13 + uv (for services/control-plane)
brew install python@3.13 uv

# Go 1.26 (for apps/foia-cli)
brew install go

# Rust 1.95 via rustup (for apps/edge-agent)
brew install rustup
rustup toolchain install 1.95.0 --profile minimal -c rustfmt -c clippy
rustup default 1.95.0

# Quality-of-life
brew install pre-commit
```

Verify everything is on PATH:

```bash
node --version       # v24.x
pnpm --version       # 10.33.x
python3.13 --version # 3.13.x
uv --version         # 0.11.x
go version           # go1.26.x
rustc --version      # 1.95.0
```

## 2. Install workspace dependencies

```bash
# Node workspaces (apps/web, apps/edge-agent, apps/foia-cli wrapper, services/control-plane wrapper)
pnpm install

# Python virtualenv for services/control-plane
cd services/control-plane && uv sync && cd -
# Optional — Epic 6 agent services (ruff in pre-commit; run `make lint-python-epic6-agents` to verify)
# cd services/cartographer && uv sync && cd -
# cd services/oracle && uv sync && cd -
# cd services/master_strategist && uv sync && cd -

# Rust build deps fetched on first cargo invocation
cd apps/edge-agent/src-tauri && cargo fetch && cd -

# Go modules fetched on first build
cd apps/foia-cli && go mod download && cd -
```

## 2b. Full monorepo verify in one go (Node + Go + `uv` + `turbo`)

The smoke command in [§4](#4-verify-the-smoke-suite) needs every toolchain and every Python tree synced. For CI-style parity on a clean machine, use the image in [`infra/docker/Dockerfile.turbo-all`](../infra/docker/Dockerfile.turbo-all) (see [`infra/docker/README-turbo-image.md`](../infra/docker/README-turbo-image.md)):

```bash
docker build -f infra/docker/Dockerfile.turbo-all -t deployai-turbo-all .
docker run --rm -v "$PWD":/repo -w /repo deployai-turbo-all
```

The default container command runs `pnpm install --frozen-lockfile`, `scripts/ci-uv-sync-all.sh`, and `pnpm turbo run test lint typecheck build` (Tauri is not compiled in that image; it matches the Node-side smoke, not a full `cargo` build). If you already have Node 24, pnpm, Go, and `uv` on your host, the same sequence is in [`scripts/run-turbo-all.sh`](../scripts/run-turbo-all.sh).

## 3. Install pre-commit hooks (one-time)

```bash
pre-commit install
```

This wires `.pre-commit-config.yaml` into `.git/hooks/pre-commit` so that formatters (prettier, ruff-format, gofmt, cargo fmt) and lightweight linters (ruff, go vet) run automatically on staged files.

`ruff` and `ruff-format` run on **staged** Python under `services/control-plane`, `services/ingest`, and the Epic 6 agents **`cartographer`**, **`oracle`**, and **`master_strategist`**. If you only touch an agent, you still get the same check before commit. To run the check on all of those service trees without relying on the hook, use `make lint-python-epic6-agents` (or `make format-python-epic6-agents` to apply `ruff format`).

**Docker + `uv` path dependencies (monorepo):** images that need sibling packages (e.g. `packages/llm-provider-py`) mirror the full repo at **`/repo/...`**, with `WORKDIR` set to the service (see `services/control-plane/Dockerfile`). When you add a new **path** dependency in a `pyproject.toml`, build context must copy every needed tree under `/repo` so `uv sync` can resolve; do not point path deps at paths outside the build context. CI and local `docker run -v $PWD:/repo` follow the same layout.

## 4. Verify the smoke suite

```bash
pnpm turbo run lint typecheck test build
```

Should report `20 successful, 20 total` across `@deployai/web`, `@deployai/edge-agent`, `@deployai/foia-cli`, `@deployai/control-plane`, and the `packages/design-tokens` / `build-storybook` fan-out added in Stories 1.4–1.5. Anything less means one of the toolchains above is missing or a version drifted.

## 4a. Verify the accessibility gate stack (Story 1.6)

The four a11y gates that `.github/workflows/a11y.yml` runs can be exercised locally. See [`docs/a11y-gates.md`](./a11y-gates.md) for the full "what each runner catches" + appeal-process reference. Quick commands:

```bash
# Static lint (fastest — matches CI job 1)
pnpm --filter @deployai/web lint

# Storybook per-story axe (matches CI job 2)
pnpm --filter @deployai/web build-storybook
pnpm dlx http-server apps/web/storybook-static --port 6006 --silent &
pnpm --filter @deployai/web storybook:test

# Playwright E2E + axe (matches CI job 3) — needs Playwright browsers:
pnpm --filter @deployai/web exec playwright install --with-deps chromium
pnpm --filter @deployai/web build
pnpm --filter @deployai/web test:e2e

# pa11y-ci (matches CI job 4) — needs puppeteer Chrome:
node node_modules/.pnpm/@puppeteer+browsers@2.13.0/node_modules/@puppeteer/browsers/lib/cjs/main-cli.js \
  install chrome@147.0.7727.57 --path "$HOME/.cache/puppeteer"
pnpm --filter @deployai/web build
pnpm --filter @deployai/web exec next start --port 3000 &
pnpm --filter @deployai/web test:a11y
```

`@axe-core/react` also logs violations to the browser console when running `pnpm --filter @deployai/web dev` — no setup required, tree-shaken out of prod builds.

## Strategist UI (`next dev`)

[`apps/web/middleware.ts`](../apps/web/middleware.ts) injects `x-deployai-role: deployment_strategist` in **`NODE_ENV=development`** when the header is missing, so you can open `/digest`, `/in-meeting`, et al. in a normal browser without an extension. Client fetches to `/api/bff/*` and `/api/internal/strategist-activity` get the same header.

[`getActorFromHeaders`](../apps/web/src/lib/internal/actor.ts) applies the **same default role in development** if the header still does not reach a Route Handler (avoids **401** on `strategist-activity` / memory-search in some `next dev` setups).

- **Disable** the default (e.g. to test 403/401 without role): `DEPLOYAI_DISABLE_DEV_STRATEGIST=1 pnpm --filter @deployai/web dev`
- **Epic 9.1 — meeting presence + poll cadence**
  - Control plane stub: `DEPLOYAI_STUB_IN_MEETING_TENANT_IDS` (comma-separated UUIDs) marks those tenants **in meeting** for `GET /internal/v1/strategist/meeting-presence`. The web app must send **`x-deployai-tenant`** with the same UUID for server-side `loadStrategistActivityForActor` to see it.
  - Client poll interval (default **30 s**, max **30 s**): set at **build** time with `NEXT_PUBLIC_DEPLOYAI_STRATEGIST_ACTIVITY_POLL_MS` (e.g. `10000` for a 10 s poll in local prod builds). Used by `StrategistShell` for `GET /api/internal/strategist-activity` while the tab is visible.
- **Production / CI** (`next start`, `next build`): no middleware injection and no actor fallback — E2E and staging use real headers or expect 403/401.
- **`/digest` 404 while `/` works:** Turbopack may have inferred the wrong workspace root (e.g. another `package-lock.json` on your machine). Remove or rename that stray lockfile, or follow [Turbopack `root`](https://nextjs.org/docs/app/api-reference/config/next-config-js/turbopack#root-directory) in `apps/web/next.config.ts` for your layout.

## 5. Run each workspace

```bash
pnpm --filter @deployai/web dev               # Next.js on :3000
pnpm --filter @deployai/edge-agent dev        # Tauri dev window (requires Rust)
pnpm --filter @deployai/control-plane dev     # FastAPI on :8000 (uvicorn --reload)
pnpm --filter @deployai/foia-cli build && apps/foia-cli/bin/foia
```

## 6. Docker sanity check (per-workspace)

```bash
docker build -f apps/web/Dockerfile -t deployai/web:dev .
docker build -f apps/foia-cli/Dockerfile -t deployai/foia-cli:dev .
docker build -f services/control-plane/Dockerfile -t deployai/control-plane:dev .
# apps/edge-agent Dockerfile only does `cargo check` — shippable bundles need native OS runners.
```

## 7. Local stack via docker-compose (Story 1.7)

The reference local stack brings up Postgres 16 (with pgvector + pgcrypto),
Redis 7, MinIO, a FreeTSA stub (Story 1.13 placeholder), the FastAPI
control-plane, and the Next.js web surface — seeded with a synthetic tenant
+ ≥ 20 canonical fixture events.

**Prerequisites:**

- Docker Desktop ≥ 4.30 (or Docker Engine + Compose v2 on Linux), ≥ 8 GB RAM allocated, ≥ 20 GB disk free.
- macOS / Linux shell. Windows: use WSL2.

**Bring up:**

```bash
make dev            # builds images, starts stack, waits for healthchecks, runs seeder
make dev-verify     # probes every service's health endpoint + /admin/runs render
```

**Expected port matrix:**

| Service        | Port        | URL                                  |
|----------------|-------------|--------------------------------------|
| web            | 3000        | http://localhost:3000                |
| control-plane  | 8000        | http://localhost:8000/health         |
| postgres       | 5432        | `psql postgresql://deployai:deployai-local-dev@localhost:5432/deployai` |
| redis          | 6379        | `redis-cli -h localhost`             |
| minio api      | 9000        | http://localhost:9000/minio/health/live |
| minio console  | 9001        | http://localhost:9001                |
| freetsa-stub   | 2020        | http://localhost:2020/health         |

**Tear down:**

```bash
make dev-down       # stops stack, removes named volumes
make dev-logs       # tail all compose logs
```

**First-run budget:** ≤ 30 minutes on a clean machine (NFR77). CI enforces
this via `.github/workflows/compose-smoke.yml`.

**Fixtures:** Seed data lives in the `fixtures.*` schema (separate from
`public` so Story 1.8's canonical-memory migrations land cleanly). Query:

```bash
docker compose --env-file infra/compose/.env -f infra/compose/docker-compose.yml \
  exec postgres psql -U deployai -d deployai -c "SELECT count(*) FROM fixtures.canonical_events;"
```

**Troubleshooting:**

| Symptom | Fix |
|---|---|
| `make dev` errors "port 3000 already in use" | Edit `infra/compose/.env` to override `WEB_PORT` (or `CONTROL_PLANE_PORT`, etc.). |
| Healthchecks time out on cold run | `make dev-down && make dev` — first run with empty layer cache may exceed the default 15-min wait. Check `make dev-logs` for which service is stalling. |
| `seed: fixtures/schema.sql not found` | Rerun from repo root; the script expects `infra/compose/seed/schema.sql` relative to itself. |
| `pgvector` / `pgcrypto` missing | Rebuild the postgres image: `docker compose build postgres && make dev-down && make dev`. Init scripts only run on an empty data volume. |
| Corpnet proxy blocks image pulls | Configure Docker Desktop → Settings → Resources → Proxies. The compose file has no hardcoded proxy. |

## Troubleshooting

| Symptom | Fix |
|---|---|
| `pnpm install` complains about frozen lockfile | `pnpm install --no-frozen-lockfile` once after pulling a branch that changed deps. |
| `tsc` fails with `exactOptionalPropertyTypes` errors on `vitest.config.ts` | Already excluded in each workspace `tsconfig.json`. If reintroduced, add to the `exclude` array. |
| `uv run pytest` can't find `control_plane` | Run from `services/control-plane/` (or `cd` there first). `pyproject.toml` sets `pythonpath = ["src"]`. |
| `cargo check` wants webkit libs on Linux | `sudo apt install libwebkit2gtk-4.1-dev libgtk-3-dev libayatana-appindicator3-dev librsvg2-dev pkg-config`. |
