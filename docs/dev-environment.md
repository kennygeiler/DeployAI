# Dev environment

The DeployAI stack is a TypeScript / Python monorepo run locally with docker-compose. There is no native desktop
component (the Tauri edge agent and Go FOIA CLI were retired 2026-05-23; see the
[archived](./archive/dev-environment.md) prior version of this doc if you need their historical setup).

---

## 1. Install runtimes

Versions are pinned in `.nvmrc`, `.tool-versions`, `.python-version`, and `pyproject.toml` per service. Homebrew
is the sanctioned macOS path; `asdf` / `apt` / direct installers work on Linux.

```bash
# Node 24 + pnpm 10
brew install node@24 pnpm
corepack enable && corepack use pnpm@10

# Python 3.13 + uv (per service)
brew install uv

# Docker (compose stack)
brew install --cask docker
```

Verify:

```bash
node --version    # v24.x
pnpm --version    # 10.x
uv --version
docker --version
```

---

## 2. Install JS dependencies

```bash
pnpm install --frozen-lockfile
```

This installs every workspace (`apps/web`, `packages/*`, `services/*` that have a `package.json`). The lockfile
is authoritative — never run `pnpm add` without explicit license in your spawn brief (see `AGENTS.md` §5).

---

## 3. Install Python dependencies per service

Each Python service owns its own `uv` env. The control plane is the heaviest:

```bash
cd services/control-plane && uv sync && cd -
cd services/cartographer  && uv sync && cd -
cd services/oracle        && uv sync && cd -
cd services/master_strategist && uv sync && cd -
cd services/ingest        && uv sync && cd -
cd services/mcp-server    && uv sync && cd -
```

---

## 4. Boot the local stack

```bash
cp infra/compose/.env.example infra/compose/.env
# Add ANTHROPIC_API_KEY to the .env (other defaults are usable).
make dev
```

`make dev` brings up postgres (with `pgvector` + Apache AGE extensions), redis, minio, the control-plane, the
web app, and the MCP-server. `make dev-verify` checks each container is healthy. `make dev-down` stops them.

---

## 5. Seed data

Three fixtures are available:

```bash
make seed-scenario-bluestate            # 26-week single engagement (deterministic insights)
# BlueState-XL (5-year, ~2.5k events): use the onboarding wizard at /onboarding
#   or POST /api/bff/onboarding/seed-bluestate-xl
# DeployAI Portfolio (5 engagements × 26w, cross-isolation stress): wizard or
#   POST /api/bff/onboarding/seed-portfolio
```

Open `http://localhost:3000/engagements` after seeding.

---

## 6. Per-workspace development

| Workspace | Run | Notes |
|---|---|---|
| `apps/web` | `pnpm --filter @deployai/web dev` | Next.js dev server (`http://localhost:3000`). BFF routes live under `src/app/api/`. |
| `services/control-plane` | `cd services/control-plane && uv run uvicorn control_plane.main:app --reload` | Compose runs it for you; override here if you need ad-hoc reloads outside compose. |
| `services/mcp-server` | `cd services/mcp-server && uv run python -m mcp_server.main` | Inbound MCP server on port 3030. |

---

## 7. Gates before commit

Per `AGENTS.md` §7, all gates green locally before `git commit`:

```bash
# CP gates (if you touched anything under services/control-plane/)
cd services/control-plane
uv run mypy src
uv run ruff check src tests alembic
uv run ruff format --check src tests alembic
uv run pytest tests/unit -x

# Web gates (if you touched anything under apps/web/)
cd apps/web
pnpm typecheck
pnpm lint
pnpm test

# Root gate (always)
cd <repo-root>
pnpm -w run format:check
```

The root `pnpm -w run format:check` is the most-missed gate. Turbo's lint task doesn't catch prettier drift.

---

## 8. Troubleshooting

| Symptom | Fix |
|---|---|
| `pnpm install` fails with engine error | Use Node 24.x per `.nvmrc`. |
| Compose stack starts but DB is empty | Confirm `alembic upgrade head` ran in the control-plane container; check `make dev` logs. |
| BFF routes return 502 / `cp_error` | Control-plane probably not healthy — `make dev-logs` then look at the `control-plane` container. |
| pgvector / AGE extension missing | Both ship in `infra/compose/postgres/Dockerfile`. Rebuild: `docker compose -f infra/compose/docker-compose.yml build postgres`. |
| `make dev` says "ANTHROPIC_API_KEY required" | Set it in `infra/compose/.env`. Agent Kenny + Cartographer both need it. |
| Agent Kenny SSE stream silent | Check `services/control-plane` logs for budget exhaustion (`OracleBudgetExhaustedError`) or LLM-provider errors. Per-tenant daily token cap is configurable. |
| Eval harness fails locally | See [`agent-kenny/eval.md`](./agent-kenny/eval.md) §Running locally + §Interpreting `cross_engagement_leak` failures. |

---

## 9. Where to learn more

- Root [`README.md`](../README.md) — feature inventory + architecture diagram
- [`docs/agent-kenny/INDEX.md`](./agent-kenny/INDEX.md) — every Agent Kenny doc
- [`docs/design/timeline-ledger.md`](./design/timeline-ledger.md) — the substrate data model
- [`docs/ops/deployment.md`](./ops/deployment.md) — hosting / production
- [`AGENTS.md`](../AGENTS.md) — sub-agent rules of the road
