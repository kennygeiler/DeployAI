# Story 1.7: docker-compose reference dev environment

Status: in-progress

## Story

As a **new engineer**,
I want a single `docker-compose up` command that brings up the complete DeployAI local stack with seeded fixtures in ≤ 30 minutes,
so that onboarding does not bottleneck on tribal knowledge and NFR77 dev-env-parity is verified in CI.

**Satisfies:** NFR77 (onboarding ≤ 30 min), NFR68 (V1 docker-compose reference build), NFR67 (shared-tenant ↔ self-hosted parity floor).

---

## Acceptance Criteria

**AC1.** `infra/compose/docker-compose.yml` boots a complete stack with one command (`make dev`). Services:

1. `postgres` — Postgres 16 with **`pgvector` + `pgcrypto`** extensions preinstalled (custom Dockerfile under `infra/compose/postgres/`). Healthcheck: `pg_isready`.
2. `redis` — `redis:7-alpine`. Healthcheck: `redis-cli ping`.
3. `minio` — `minio/minio:<pinned>` with `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` from `.env`. Healthcheck: `/minio/health/live`.
4. `freetsa-stub` — lightweight RFC 3161 stub (nginx + static response or tiny python/flask) — returns HTTP 200 on `/tsr`. Placeholder for Story 1.13.
5. `control-plane` — FastAPI service built from `services/control-plane/Dockerfile`. `depends_on` with `condition: service_healthy` for postgres+redis. Healthcheck: `GET /health`.
6. `web` — Next.js app built from `apps/web/Dockerfile`. `depends_on: service_started` for control-plane. Healthcheck: `GET /` returns 200.

**AC2.** Extensions file `infra/compose/postgres/init/01-extensions.sql` runs on first boot and creates `pgvector` + `pgcrypto` in the `deployai` database. Postgres Dockerfile inherits from `pgvector/pgvector:pg16` (official image with pgvector pre-bundled); pgcrypto is a built-in contrib module activated by the init SQL.

**AC3.** `infra/compose/.env.example` documents every environment variable the stack consumes (Postgres creds, MinIO creds, control-plane `DATABASE_URL`, `REDIS_URL`, `S3_ENDPOINT`, `TSA_URL`). `make dev` copies it to `.env` on first run if `.env` is missing.

**AC4.** `services/control-plane` gains a **`GET /health`** endpoint (alias of `/healthz`) to satisfy the AC's "`/health` endpoint" language literally. `/healthz` remains for k8s parity. Both return `{"status":"ok","service":"control-plane","version":"<pkg-version>"}`.

**AC5.** `apps/web` Dockerfile is fixed to copy `packages/design-tokens/` into the build context so `@deployai/design-tokens/tailwind` resolves during the Next build (same root cause as the Story 1.6 CI topology bug — the Dockerfile must match Turborepo's `^build` graph, not bypass it).

**AC6.** `infra/compose/seed/seed.sh` is idempotent and populates a **`fixtures` Postgres schema** (kept deliberately separate from the `public` schema Story 1.8 will author — no collision with the canonical memory tables that land later). Creates:

- `fixtures.tenants` — 1 row (synthetic tenant `acme-pilot`, UUID v7, name).
- `fixtures.identity_nodes` — ≥ 5 stakeholder rows (id, tenant_id, display_name, role).
- `fixtures.canonical_events` — ≥ 20 synthetic events (id, tenant_id, event_type, payload jsonb, created_at).
- `fixtures.phase_states` — 1 sample phase row for the synthetic tenant (phase_id ∈ {discovery, research, planning, drafting, review, decision, ratified}, phase_state, updated_at).

Schema DDL lives at `infra/compose/seed/schema.sql`; data generation lives at `infra/compose/seed/seed.sh` (uses `psql` inside the `postgres` container via `docker compose exec`). The script is safe to re-run (TRUNCATE + INSERT).

**AC7.** `apps/web/src/app/admin/runs/page.tsx` is a **minimal stub route** that renders a placeholder ("Admin — Runs (stub; Story 1.16 ships the real admin shell)") so `http://localhost:3000/admin/runs` responds 200 with no errors — satisfies the "admin shell at `/admin/runs` renders without error" AC from the epic without pulling Story 1.16's scope forward.

**AC8.** Root `Makefile` exposes:

- `make dev` → copies `.env.example` to `.env` if missing, runs `docker compose -f infra/compose/docker-compose.yml up -d --build`, waits for all healthchecks to pass, runs `seed.sh` once.
- `make dev-verify` → curls every service's health endpoint (`postgres` via `pg_isready`, `redis` via `redis-cli ping`, `minio` via `curl :9000/minio/health/live`, `freetsa-stub` via `curl :2020/tsr`, `control-plane` via `curl :8000/health`, `web` via `curl :3000/`). Exits non-zero on any failure.
- `make dev-down` → `docker compose down -v` (volumes cleared).
- `make dev-logs` → tails compose logs.
- `make compose-smoke` → CI entry point: `make dev && make dev-verify` with a hard 30-min ceiling (`timeout 1800 …`).

**AC9.** `make dev-verify` includes a **page-render check** for `/` and `/admin/runs` (HTTP 200 + body contains a known string) — not just a TCP probe — so AC7's "render without error" is actually verified.

**AC10.** `.github/workflows/compose-smoke.yml` runs `make compose-smoke` on every PR touching `infra/**`, `services/**`, `apps/web/Dockerfile`, `Makefile`, or the workflow itself (path filter). Workflow conventions mirror `a11y.yml` and `ci.yml`:

- `ubuntu-24.04`, `timeout-minutes: 35` (30-min stack ceiling + buffer), `concurrency` group per workflow+ref, `permissions: contents: read`, every external action SHA-pinned with `# vX.Y.Z` comment, `defaults.run.shell: bash`.
- Uploads `docker compose logs` as `compose-logs.txt` artifact on failure (14-day retention).
- Job name: `compose-smoke` (plain, stable for branch protection matchers).

**AC11.** `.github/workflows/README.md` adds `compose-smoke.yml` to the "Current workflows" table and appends `compose-smoke / compose-smoke` to the "Required checks on `main`" list (now 10 total).

**AC12.** `docs/dev-environment.md` gets a §"Local stack via docker-compose" section that:

- Lists prerequisites (Docker Desktop ≥ 4.3x with ≥ 8 GB RAM; ≥ 20 GB disk free).
- Walks through `cp infra/compose/.env.example infra/compose/.env` → `make dev` → expected output → port matrix (5432 postgres, 6379 redis, 9000/9001 minio, 2020 freetsa-stub, 8000 control-plane, 3000 web).
- Troubleshooting (port-conflict, "pgvector missing" → rebuild postgres image, "seed fails" → `make dev-down && make dev`, DNS/proxy corp-network notes).

`docs/repo-layout.md` gets an `infra/compose/` section describing the directory structure.

**AC13.** `turbo.json` + root `package.json` gain no new Turbo tasks for compose (compose is orchestrated by `make`, not `turbo` — different primitive). Root `package.json` MAY gain `"compose:smoke": "make compose-smoke"` convenience script.

**AC14.** `.gitignore` adds `infra/compose/.env` (never commit secrets); keeps `.env.example` tracked. Adds `infra/compose/postgres/data/` and any other bind-mount directories (prefer named Docker volumes, but guard against accidental bind-mount configs).

**AC15.** Existing gates stay green: `pnpm turbo run lint typecheck test build` → 20/20; `a11y.yml` → 4/4; `ci.yml` → 5/5 (or 4/5 with neutral dependency-review). `pnpm install --frozen-lockfile` clean. `pnpm format:check` clean.

**AC16.** Scope fence — what this story does **NOT** do:

- **No observability stack** (Grafana/Prometheus/Loki/Tempo). Deferred to Story 12.10.
- **No Story 1.8 canonical-memory schema.** Seed tables live in a separate `fixtures` schema that Story 1.8 will not touch.
- **No authn/authz on control-plane.** Story 1.9 + Epic 2.
- **No full admin shell** — `/admin/runs` is a stub. Story 1.16.
- **No Helm.** V1.5 (Story 14.6).
- **No edge-agent in compose** — the Tauri Dockerfile is a `cargo check`, not a runnable service. Story 1.15 + Epic 11.
- **No go CLI in compose** — `apps/foia-cli` is a build-time binary, not a long-running service.
- **No TLS/SSO wiring** for compose — plain HTTP on localhost.
- **No multi-tenant seed** — one synthetic tenant is enough for onboarding + Story 4.4 golden-query authoring.

---

## Tasks / Subtasks

### Phase 0 — Prep
- [ ] Verify main is green locally; pull latest; run `pnpm install --frozen-lockfile && pnpm turbo run lint typecheck test build` → 20/20.
- [ ] Verify Docker Desktop running.

### Phase 1 — Compose scaffold + infra services (AC1–AC3)
- [ ] Create `infra/compose/` directory tree: `docker-compose.yml`, `.env.example`, `postgres/Dockerfile`, `postgres/init/01-extensions.sql`, `freetsa-stub/Dockerfile`, `freetsa-stub/tsr-stub.py` (or nginx).
- [ ] Postgres image: `FROM pgvector/pgvector:pg16`; copy `init/*.sql` into `/docker-entrypoint-initdb.d/` so extensions auto-create on first boot in the `deployai` database.
- [ ] FreeTSA stub: tiny Python `http.server` subclass or nginx returning HTTP 200 on any path. Pick whichever is smaller (nginx probably).
- [ ] Compose services: `postgres`, `redis`, `minio`, `freetsa-stub` with healthchecks, named volumes (`pg_data`, `redis_data`, `minio_data`), no bind-mounts.
- [ ] Verify `docker compose up -d postgres redis minio freetsa-stub && docker compose ps` shows 4/4 healthy.

### Phase 2 — App services in compose (AC4, AC5)
- [ ] Add `GET /health` endpoint to `services/control-plane/src/control_plane/main.py` (alias of `/healthz`, same body + `service` + `version` fields). Update `test_healthz.py` or add a new `test_health.py` covering both paths.
- [ ] Fix `apps/web/Dockerfile` to copy `packages/design-tokens/` so the build doesn't fail on the `@deployai/design-tokens/tailwind` import. Verify `docker build -f apps/web/Dockerfile .` succeeds from a clean state.
- [ ] Add `control-plane` service to compose (build context `.`, dockerfile `services/control-plane/Dockerfile`, env: `DATABASE_URL`, `REDIS_URL`, healthcheck via `python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"` or `curl`).
- [ ] Add `web` service to compose (build context `.`, dockerfile `apps/web/Dockerfile`, env: `NEXT_PUBLIC_CONTROL_PLANE_URL`, healthcheck via wget/curl on `/`).
- [ ] Verify `docker compose up -d --build` brings all 6 services healthy.

### Phase 3 — Seed fixtures (AC6)
- [ ] Author `infra/compose/seed/schema.sql` — `CREATE SCHEMA IF NOT EXISTS fixtures;` + 4 tables (tenants, identity_nodes, canonical_events, phase_states).
- [ ] Author `infra/compose/seed/seed.sh` — bash script that `docker compose exec -T postgres psql -U deployai -d deployai -f -` pipes schema.sql then data INSERTs (≥20 events, ≥5 stakeholders, 1 phase row). Idempotent via `TRUNCATE ... CASCADE` at the top.
- [ ] Verify `bash infra/compose/seed/seed.sh` returns 0 and subsequent `psql -c "SELECT count(*) FROM fixtures.canonical_events"` reports ≥ 20.

### Phase 4 — Admin stub route (AC7, AC9)
- [ ] Create `apps/web/src/app/admin/runs/page.tsx` — plain RSC that renders an `<h1>` + placeholder body. Add `id="main"` to its `<main>` for skip-link parity with `/`. Verify lint/typecheck/a11y gate all clean.

### Phase 5 — Makefile (AC8, AC9)
- [ ] Author root `Makefile` with POSIX-safe targets: `dev`, `dev-verify`, `dev-down`, `dev-logs`, `compose-smoke`, `help`.
- [ ] `dev-verify` runs a sequence of curl/pg_isready/redis-cli probes AND a `curl --fail http://localhost:3000/admin/runs | grep -q "Admin"` render check.
- [ ] Verify `make dev && make dev-verify && make dev-down` works end-to-end on a clean machine.

### Phase 6 — CI workflow (AC10, AC11)
- [ ] Author `.github/workflows/compose-smoke.yml` — `ubuntu-24.04`, `timeout-minutes: 35`, path filter, concurrency, SHA-pinned actions.
- [ ] Cache docker layers via `actions/cache` keyed on lockfile + Dockerfiles.
- [ ] Upload `docker compose logs` on failure.
- [ ] Update `.github/workflows/README.md` — add `compose-smoke.yml` row + 10th required check string.

### Phase 7 — Docs (AC12)
- [ ] Append "Local stack via docker-compose" section to `docs/dev-environment.md`.
- [ ] Append "infra/compose/" section to `docs/repo-layout.md`.

### Phase 8 — Plumbing (AC13, AC14)
- [ ] `.gitignore`: add `infra/compose/.env`, `infra/compose/**/data/`.
- [ ] Root `package.json`: optional `"compose:smoke": "make compose-smoke"` script.

### Phase 9 — Verification + PR
- [ ] `pnpm install --frozen-lockfile` clean.
- [ ] `pnpm turbo run lint typecheck test build` → 20/20.
- [ ] `make dev && make dev-verify && make dev-down` → green locally.
- [ ] `pnpm format:check` clean; `actionlint .github/workflows/compose-smoke.yml` clean.
- [ ] Push branch; open PR; watch `compose-smoke` check go green alongside existing gates.
- [ ] Update sprint-status `1-7 → review`.

---

## Dev Notes

### Why a separate `fixtures` schema instead of the real canonical-memory tables

Story 1.7 ships **before** Story 1.8 (canonical memory schema). The epic's AC asks for "≥ 20 canonical events, ≥ 5 stakeholders, sample phase state" as seed data, but the real `canonical_memory_events` / `identity_nodes` / `phase_states` tables with their RLS policies, append-only triggers, UUID v7 primary keys, and tenant-scoped shapes don't land until Story 1.8. Rather than pre-build a half-baked version of those tables and cause expand-contract conflicts later, Story 1.7 uses a `fixtures` Postgres schema that:

1. Has intentionally **lightweight shapes** (UUID PKs, tenant_id, payload JSONB, timestamps — nothing more).
2. Is **scoped** so Story 1.8's migrations run in `public` without collision.
3. Can be **dropped entirely** in Story 1.8's final phase once the real tables land — or left as a dev-only fixture that Story 4.4 keeps using for golden-query authoring.

This keeps Story 1.7 honest (the AC's "seeded tenant" is real data an engineer can query) without over-committing schema decisions that belong to Story 1.8.

### Why `/admin/runs` is a stub

The AC says "`/admin/runs` renders without error". Story 1.16 (later in Epic 1) builds the real admin shell with AuthzResolver, etc. Shipping a stub page satisfies the "renders" bar without forcing Story 1.7 to pull Epic 2's authz work forward.

### `/health` vs `/healthz`

The AC literally says "`/health` endpoint". The control-plane implementation from Story 1.3 has `/healthz` (k8s convention). Story 1.7 adds `/health` as an alias — both are cheap to serve, and this lets k8s users stay on `/healthz` while the compose AC reads true.

### apps/web Dockerfile fix

The current `apps/web/Dockerfile` (line 19) copies `apps/web/` but **not** `packages/design-tokens/`. Since `globals.css` imports `@deployai/design-tokens/tailwind`, the Docker build fails exactly like Story 1.6's CI did before we switched to `turbo run --filter=`. Fix: `COPY packages/design-tokens ./packages/design-tokens` before the build step, and ensure the `deps` stage copies `packages/design-tokens/package.json` too.

### 30-minute budget

GitHub Actions ubuntu-24.04 cold starts, pulls postgres/redis/minio images (~600 MB total), builds control-plane + web (~2–5 min each), brings the stack up, and seeds. Realistic first-run: 10–15 min. The 30-min ceiling is generous. If it ever drifts past 25, flag it.

### Scope anti-patterns (don't do)

1. **Don't add Grafana/Prometheus/Loki/Tempo** — AR23 lists them but Story 1.7 AC explicitly omits them. Story 12.10 wires observability.
2. **Don't pre-build Story 1.8's schema** — use `fixtures` schema.
3. **Don't use bind mounts for Postgres data** — named volumes only, so `make dev-down` cleans cleanly.
4. **Don't pin MinIO or Redis to `:latest`** — pin a specific digest or tag for reproducibility.
5. **Don't require corpnet proxy config** in the Makefile — document it in troubleshooting but don't hardcode.
6. **Don't start the edge-agent or foia-cli in compose** — they aren't server processes.
7. **Don't require users to run `pnpm install` before `make dev`** — the Dockerfiles own their own install.

---

## Testing Standards

- **New:** `services/control-plane/tests/unit/test_health.py` asserts both `/health` and `/healthz` return 200 with expected body.
- **CI smoke:** `compose-smoke.yml` IS the integration test — full stack bring-up is the only real regression signal.
- **Local:** `make dev-verify` is the engineer's 10-second sanity check.
- **No unit tests for seed.sh** — it's a bash script; shellcheck + manual verification is enough.

---

## Source Hints

- `_bmad-output/planning-artifacts/epics.md` lines 695–710 — Story 1.7 user story + AC.
- `_bmad-output/planning-artifacts/prd.md` lines 1672–1689 — NFR67/68/77 canonical text.
- `_bmad-output/planning-artifacts/architecture.md` lines 307–314 — compose service list + observability.
- `_bmad-output/planning-artifacts/architecture.md` lines 672–677 — `infra/compose/` tree.
- `_bmad-output/planning-artifacts/epics.md` lines 1209–1214 — Story 4.4 consumes 1.7's seed tenant.
- `_bmad-output/planning-artifacts/epics.md` lines 2392–2405 — Story 12.9 consumes 1.7's compose.
- `_bmad-output/planning-artifacts/epics.md` line 2702 — dependency graph 1.6 → 1.7 → 1.8.
- `services/control-plane/src/control_plane/main.py` lines 14–17 — `/healthz` (alias target).
- `services/control-plane/Dockerfile` — control-plane container.
- `apps/web/Dockerfile` — web container (needs design-tokens fix).
- `.github/workflows/a11y.yml` — workflow conventions to mirror.
- `.github/workflows/README.md` — required-checks list.
- `docs/dev-environment.md` — Story 1.3 dev docs (extend, don't replace).
- `pgvector/pgvector` Docker Hub — https://hub.docker.com/r/pgvector/pgvector

---

## Risks

1. **apps/web Dockerfile is currently broken** — building it from scratch outside Turbo fails on the design-tokens import. Fixing this is a prerequisite; any CI run of `compose-smoke.yml` is DOA until it lands.
2. **30-min budget on GHA cold runners** — plausible but not guaranteed. If cold pulls + builds take > 25 min, we need docker-layer caching (`actions/cache` or `buildx` `--cache-to`).
3. **pgvector/pgvector image stability** — official, actively maintained, but mirror availability from GHA runners varies.
4. **FreeTSA-stub scope creep** — Story 1.13 will ship the real TSA client. The stub here must not grow beyond "HTTP 200 on /tsr" or it competes with 1.13's scope.
5. **Seed schema drift vs Story 1.8** — using a separate `fixtures` schema mitigates, but Story 1.8's author needs to know about it. Dev Notes flag it.
6. **Docker Desktop on Apple Silicon** — arm64 variants of all images needed. `pgvector/pgvector:pg16` publishes arm64; Redis/MinIO/FreeTSA stub are trivial. Verify during Phase 1.
7. **Port conflicts** — 3000 / 5432 / 6379 / 9000 / 8000 are commonly taken. Document override via `.env`.

---

## Dev Agent Record

### Agent Model Used
claude-opus-4.7 (parent agent).

### Debug Log References
_(populated during Phase 1–9)_

### Completion Notes List
_(populated at Phase 9)_

### File List
_(populated at Phase 9)_

---

## Change Log

| Date | Author | Summary |
|------|--------|---------|
| 2026-04-23 | bmad-create-story (lean) | Compact story context authored in one pass to avoid ceremony overhead. 16 ACs, 9 phases, key design decisions baked in: separate `fixtures` Postgres schema (avoids Story 1.8 collision), `/admin/runs` stub (avoids Story 1.16 scope), `/health` as alias of `/healthz`, apps/web Dockerfile design-tokens fix (root cause from Story 1.6 CI). Observability explicitly deferred to Story 12.10. Status → in-progress. |
