# DeployAI

[![Node](https://img.shields.io/badge/node-24.x-339933?logo=nodedotjs)](./.nvmrc)
[![pnpm](https://img.shields.io/badge/pnpm-workspace-f69220?logo=pnpm)](./pnpm-workspace.yaml)
[![Turbo](https://img.shields.io/badge/build-turbo-000000?logo=turborepo)](./turbo.json)
[![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python)](./services/control-plane/.python-version)
[![License](https://img.shields.io/badge/license-UNLICENSED-lightgrey.svg)](./README.md#license)

> **A deployment matrix you can ask questions of.** DeployAI is a tool for deployment / forward-deployed teams who lose
> insight in the seams — Slack threads, sales-ops handoffs, security reviews, customer Notion pages, the ticket queue.
> Capture each engagement as a typed, time-travelable property graph; let **Agent Kenny** — a multi-step LLM agent with
> citation discipline — answer questions, walk causal chains, and surface cross-team patterns without hallucinating.

---

## Quickstart

```bash
git clone https://github.com/kennygeiler/DeployAI.git && cd DeployAI
pnpm install --frozen-lockfile
cp infra/compose/.env.example infra/compose/.env       # add ANTHROPIC_API_KEY
make dev                                               # full local stack (web, control-plane, postgres, redis, minio, mcp-server)
make seed-scenario-bluestate                           # 26-week ground-truth engagement
open http://localhost:3000/engagements
```

Then:

1. Click **BlueState Health — Member Portal Replatform**.
2. Scrub the time-slider on the matrix view — every node carries its provenance back to source events.
3. Open the **Agent Kenny** chat panel. Ask: *"What concerns were raised about the Active Directory migration before
   we approved it in W22?"* Kenny calls tools, walks the causal chain, cites every claim inline, and runs an
   adversarial reviewer over its own reply before sending it.
4. Visit `/admin/agent-kenny-dashboard` for hallucination rate, tool-call distribution, latency percentiles, and lint
   flag counts — populated from the same eval harness that gates CI.

For a denser fixture, the onboarding wizard exposes two more seeds: **BlueState-XL** (5-year single-engagement,
~2.5k ledger events, ~70 stakeholders) and **DeployAI Portfolio** (5 sibling engagements × 26 weeks, used to verify
tenant + engagement isolation).

### Cloud deploy (Fly.io + Cloudflare Access)

```bash
brew install flyctl && fly auth login
# Create apps + Postgres + Redis; set secrets — see docs/ops/cloud-deploy.md §2-3
scripts/cloud-deploy.sh        # deploys all 5 services in order
# Then wire Cloudflare Access in front of app.<your-domain> and api.<your-domain>
# — see docs/ops/cloud-deploy.md §5
```

After the first manual deploy works, set the `FLY_API_TOKEN` repo secret
and the [`cloud-deploy.yml`](./.github/workflows/cloud-deploy.yml)
workflow auto-redeploys on every push to `main`, writing live URLs back
to GitHub's Environments UI (repo sidebar + per-commit "View deployment"
links). See `docs/ops/cloud-deploy.md §3.1`.

Single-tenant pilot cost: ~$5-30/mo + LLM usage (Claude pay-as-you-go + Voyage embeddings). Cloudflare Access
free tier covers up to 50 users.

Full runbook: [`docs/ops/cloud-deploy.md`](./docs/ops/cloud-deploy.md). Architecture / trust boundaries:
[`docs/ops/cloud-deploy-architecture.md`](./docs/ops/cloud-deploy-architecture.md).

---

## What's in the box

| Surface | What it does | Where it lives |
|---|---|---|
| **Engagement matrix** | Typed property graph of stakeholders / systems / decisions / risks / commitments / opportunities. Time-travel slider over daily snapshots. Provenance drawer on every node. | `apps/web/src/app/engagements/[engagementId]` |
| **Timeline ledger** | Append-only causal-graph log. Every state change emits a `ledger_event` with `caused_by` + `affects` edges. Backbone of audit + chain-walking. | `services/control-plane/src/control_plane/ledger/` |
| **Agent Kenny (chat)** | Multi-step LangGraph agent — retrieve → reason → tool-call → verify citations → adversarial-review → persist + audit. 12 internal tools, optional outbound MCP tools, hard tenant scoping, only-write tool is `propose_action`. | `services/control-plane/src/control_plane/agents/agent_kenny/` |
| **Citation discipline** | Every `[event:UUID]` / `[node:UUID]` / `[insight:UUID]` in a reply is regex-extracted, DB-checked against the current tenant + engagement, and either verified, revised, or flagged. Cross-engagement leak → hard reject + security ledger event. | `agents/agent_kenny/nodes/citations.py` |
| **Adversarial review** | Haiku-class auditor model reads Kenny's reply and the evidence, lists unstated assumptions / overreach / unsupported claims. Concerns emit `agent_audit_concern` ledger events for human review. | `agents/agent_kenny/nodes/adversarial.py` |
| **Compounding synthesis** | Background workers refresh `matrix_insights` rows on every relevant ledger emit. Insights persist with per-claim provenance and `source_event_ids`; lint worker marks them stale on upstream change. | `services/control-plane/src/control_plane/workers/synthesizer.py`, `wiki_lint.py` |
| **MCP inbound server** | Standalone uvicorn service (port 3030). Third-party MCP clients (Claude Desktop, IDE plugins) authenticate with tenant API keys + read the matrix + ledger via the Model Context Protocol. Read-only — `propose_action` is not exposed. | `services/mcp-server/` |
| **MCP outbound (Kenny → 3rd party)** | Tenant admins enable connectors from a curated catalog. At loop start Kenny merges those tools into its registry, namespaced (`slack.search_messages`, etc.). Kill-switch + per-tool / per-MCP / per-tenant rate limits. Slack OAuth is wired end-to-end; Linear / GDrive / Notion / GitHub return `501` until per-connector flows ship. | `agents/agent_kenny/mcp_client.py`, `mcp_loader.py`, `mcp_kill_switch.py` |
| **pgvector fuzzy fallback** | `vector(1024)` columns on `ledger_events`, `matrix_nodes`, `matrix_insights`, `oracle_chat_turns`; HNSW indexes; Voyage-3 embedder worker drains a job queue. `vector_search` tool is the fallback path — curated synthesis is the hot path. | migrations `0050_pgvector_embeddings.py`, `workers/embedder.py`, `agents/tools/search.py` |
| **Eval harness** | 30 hand-curated golden questions against BlueState-XL: direct lookup, causal chain, "I don't know" negatives, cross-engagement protection probes, multi-hop. Nightly 5-question sample + weekly full set in CI. Cross-engagement leak fails the build. | `services/control-plane/tests/golden/agent_kenny/`, `.github/workflows/agent-kenny-eval.yml` |
| **Admin dashboard** | Hallucination rate (7d trend), tool-call distribution, p50 / p95 / p99 latency, "I don't know" rate, lint flag counts, top-cited events / nodes, adversarial concerns. | `apps/web/src/app/(strategist)/admin/agent-kenny-dashboard/` |
| **Six statistical analyzers** | `engagement_silence`, `decision_cycle_slowdown`, `risk_open_rate`, `stakeholder_churn`, `extractor_acceptance_drift`, `decision_provenance_summary`. Pure SQL except the last (LLM-narrated). | `services/control-plane/src/control_plane/intelligence/` |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│  apps/web (Next.js 16, App Router, React 19)                                      │
│  ── engagements portfolio, detail, timeline, matrix time-slider                   │
│  ── Agent Kenny chat panel (SSE, intermediate thinking / tool_call / citation     │
│     chips render above the streaming reply)                                       │
│  ── admin: Agent Kenny dashboard, MCP integrations, kill-switch, API keys         │
└─────────────────────────────────┬────────────────────────────────────────────────┘
                                  │  BFF (Next.js server routes, Zod-narrowed)
                                  ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│  services/control-plane (FastAPI + async SQLAlchemy 2.x)                          │
│                                                                                  │
│   Domain / API           Agents                       Workers                    │
│   ──────────────         ──────────                   ────────                   │
│   matrix CRUD            cartographer (extraction)    synthesizer                │
│   ledger emitter         agent_kenny (LangGraph)      wiki_lint                  │
│   snapshot routes        ├─ retrieve / llm_call       embedder (Voyage-3)        │
│   intelligence (analyzers)  tool_dispatch / revise                               │
│   tenant_mcp_configs     ├─ citations / adversarial                              │
│   eval runner            └─ persist + audit                                      │
└─────────────────────────────────┬────────────────────────────────────────────────┘
                                  │
              ┌───────────────────┼───────────────────────┐
              ▼                   ▼                       ▼
┌────────────────────┐  ┌────────────────────┐  ┌──────────────────────────────┐
│ Postgres 16        │  │ services/mcp-server│  │ Outbound MCP (per tenant)    │
│ + pgvector (HNSW)  │  │ (inbound MCP, 3030)│  │ slack-mcp wired; linear,     │
│ + Apache AGE       │  │ tenant API keys,   │  │ gdrive, notion, github stubs │
│ ledger / matrix /  │  │ read-only matrix + │  │ — admin kill-switch +        │
│ insights / agent   │  │ ledger exposure    │  │ allow-list enforced server-  │
│ audit traces       │  │                    │  │ side, never client-side      │
└────────────────────┘  └────────────────────┘  └──────────────────────────────┘
        │
        ▼
┌────────────────────┐  Redis (queues, rate-limit windows)
│ MinIO (S3-compat)  │  Anthropic SDK (Claude Sonnet 4.7 primary, Haiku 4.5 adversarial)
└────────────────────┘  Voyage-3 (1024-dim embeddings)
```

Read [`docs/agent-kenny/ethos.md`](./docs/agent-kenny/ethos.md) for *why* the substrate is shaped this way (the
ledger is the wiki; Kenny is its disciplined librarian; every claim cites its source; every synthesis compounds).
Read [`docs/agent-kenny/scope-v2.md`](./docs/agent-kenny/scope-v2.md) for the phase-by-phase how — now historical
record, every phase is shipped.

---

## Tech stack

| Layer | Tooling |
|---|---|
| Frontend | Next.js 16 (App Router, React 19), TypeScript strict, Tailwind, shadcn primitives, Zod at every BFF boundary |
| Backend | FastAPI, async SQLAlchemy 2.x, Alembic, Pydantic v2, `uv` for env mgmt, `ruff` + `mypy` strict |
| Database | Postgres 16 + `pgvector` (HNSW) + Apache AGE (Cypher over `matrix_nodes` / `matrix_edges` graph view) |
| LLM | Anthropic Claude — Sonnet 4.7 (primary), Haiku 4.5 (adversarial reviewer). Voyage-3 (1024-dim) embeddings |
| Agent framework | LangGraph for the multi-step state machine. Anthropic SDK direct for tool-use; LangChain itself is rejected |
| Agent protocol | Model Context Protocol (MCP) — inbound server + outbound client (catalog: slack / linear / gdrive / notion / github) |
| Infra (local) | docker-compose. Postgres / Redis / MinIO / MCP-server / web / control-plane all `make dev` |
| Infra (cloud) | Fly.io (5 apps: postgres / control-plane / web / mcp-server / embedder) + Cloudflare Access (free-tier email allowlist) |
| Build / monorepo | pnpm workspaces + Turborepo on the TS side; uv per Python service |

---

## Repository layout

| Path | Role |
|---|---|
| `apps/web/` | Next.js — engagement portfolio, detail, timeline, matrix time-slider, Agent Kenny chat panel, admin dashboards, BFF routes (Zod-narrowed) |
| `services/control-plane/` | FastAPI — domain models, internal APIs, agents (Cartographer + Agent Kenny LangGraph), workers (synthesizer, lint, embedder), analyzers, MCP outbound client |
| `services/mcp-server/` | Standalone uvicorn MCP-protocol server — third-party MCP clients query the matrix + ledger read-only with tenant API keys |
| `services/cartographer/`, `services/ingest/`, `services/oracle/`, `services/master_strategist/` | Per-domain Python services (extraction, ingest, legacy single-shot agents kept as compatibility shims) |
| `packages/llm-provider-py/` | `LLMProvider` protocol + Anthropic / OpenAI / stub impls; streaming + tool-use through `chat_complete_stream_with_tools` |
| `packages/authz/` | TS + Python role/action matrix (shared) |
| `packages/contracts/`, `packages/design-tokens/`, `packages/shared-ui/` | Cross-workspace types + design system |
| `infra/compose/` | Reference local stack — docker-compose, seed scripts (BlueState 26-week, BlueState-XL 5-year, Portfolio 5-engagement) |
| `infra/fly/` | Cloud deploy — fly.toml per service (postgres / control-plane / web / mcp-server / embedder). See `docs/ops/cloud-deploy.md` |
| `scripts/cloud-deploy.sh` | Wrapper script: deploys all 5 Fly apps in the right order |
| `docs/agent-kenny/` | The hub for Agent Kenny — start at [`docs/agent-kenny/INDEX.md`](./docs/agent-kenny/INDEX.md) |
| `docs/security/` | Threat models — MCP outbound boundary, cross-tenant fuzz, tenant isolation, self-host attack surface |
| `docs/design/` | Engineering design records — timeline ledger, post-F polish, citation envelope |
| `docs/product/` | Product spec + agent design records (Cartographer, synthesis agents) |
| `docs/archive/` | Superseded planning artifacts — preserved for git history, not authoritative |
| `briefs/` | Sub-agent spawn briefs (gitignored working artifacts; see `AGENTS.md`) |

---

## Where to find more

**Start here:**

- [`docs/agent-kenny/INDEX.md`](./docs/agent-kenny/INDEX.md) — every Kenny-related doc with one-line summary
- [`docs/agent-kenny/ethos.md`](./docs/agent-kenny/ethos.md) — architectural rationale (the load-bearing doc)
- [`docs/agent-kenny/scope-v2.md`](./docs/agent-kenny/scope-v2.md) — phase-by-phase build history (Phases 0–6 all shipped)
- [`docs/agent-kenny/eval.md`](./docs/agent-kenny/eval.md) — the 30-golden-question harness and CI cadence

**For platform / infra:**

- [`docs/design/timeline-ledger.md`](./docs/design/timeline-ledger.md) — core data model: ledger, snapshots, analyzers, provenance
- [`docs/security/mcp-outbound-threat-model.md`](./docs/security/mcp-outbound-threat-model.md) — Phase 5 STRIDE + §9.4 checklist
- [`docs/security/tenant-isolation.md`](./docs/security/tenant-isolation.md) — the three-layer tenant isolation discipline
- [`docs/security/cross-tenant-fuzz.md`](./docs/security/cross-tenant-fuzz.md) — the CI fuzz harness that pins it

**For operators / pilots:**

- [`docs/dev-environment.md`](./docs/dev-environment.md) — toolchains, pnpm + uv workflows, compose stack
- [`docs/ops/cloud-deploy.md`](./docs/ops/cloud-deploy.md) — Fly.io + Cloudflare Access operator runbook (5 services, secrets, smoke checks)
- [`docs/ops/cloud-deploy-architecture.md`](./docs/ops/cloud-deploy-architecture.md) — topology + trust boundaries + where each secret lives
- [`infra/fly/`](./infra/fly/) — fly.toml per service (control-plane / web / mcp-server / embedder / postgres)
- [`scripts/cloud-deploy.sh`](./scripts/cloud-deploy.sh) — wrapper for the 5 `fly deploy` calls in order
- [`docs/ops/deployment.md`](./docs/ops/deployment.md) — host requirements, env vars (legacy single-host doc)
- [`docs/ops/observability.md`](./docs/ops/observability.md) — JSON logs, Prometheus metrics, OTLP
- [`docs/ops/backup.md`](./docs/ops/backup.md) — `make backup` + retention

---

## Verifying a clean checkout

```bash
pnpm install --frozen-lockfile
pnpm turbo run lint typecheck test build    # CI gate (web + TS workspaces)
pnpm -w run format:check                    # prettier (CI catches this independently)

cd services/control-plane                   # CP gate
uv run mypy src
uv run ruff check src tests alembic
uv run ruff format --check src tests alembic
uv run pytest tests/unit -x
```

The repo's CI runs the same plus compose-smoke, canonical-memory-schema, cross-tenant fuzz, CVE scan, SBOM
generation, and the nightly / weekly Agent Kenny eval (`.github/workflows/agent-kenny-eval.yml`).

---

## Maturity

End-to-end demo on real data via the BlueState Health 26-week seed, the BlueState-XL 5-year seed, and the
DeployAI-Portfolio 5-engagement cross-isolation seed. v2 ship complete: Agent Kenny multi-step LangGraph loop,
citation verification + adversarial review, MCP inbound + outbound, pgvector fuzzy fallback, golden-question
eval harness in CI, hallucination dashboard. No paying customers yet — the next milestone is putting it in front
of a real deployment team with their own engagement data.

**Cloud deploy:** Fly.io + Cloudflare Access configs and operator runbook landed alongside v2. See
[`docs/ops/cloud-deploy.md`](./docs/ops/cloud-deploy.md) for the step-by-step (apps, secrets, Cloudflare
Access wiring, smoke checks, day-2 ops, cost notes, teardown). The local-compose stack remains the
fastest way to demo; cloud is for when you want to put it in front of a customer.

---

## License

UNLICENSED — see [`package.json`](./package.json) `license` field.
