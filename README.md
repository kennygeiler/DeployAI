# DeployAI

[![Node](https://img.shields.io/badge/node-24.x-339933?logo=nodedotjs)](./.nvmrc)
[![pnpm](https://img.shields.io/badge/pnpm-workspace-f69220?logo=pnpm)](./pnpm-workspace.yaml)
[![Turbo](https://img.shields.io/badge/build-turbo-000000?logo=turborepo)](./turbo.json)
[![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python)](./services/control-plane/.python-version)
[![License](https://img.shields.io/badge/license-UNLICENSED-lightgrey.svg)](./README.md#license)

> **Deal relationship memory you can ask questions of — with receipts.** DeployAI is for deployment and
> forward-deployed teams running long, messy engagements where the truth lives in the seams: Slack threads,
> email chains, meeting transcripts, handoffs. It captures each engagement as a typed, evidence-linked
> property graph on an append-only event ledger, and puts **Agent Kenny** on top — a checkpointed multi-step
> LLM agent that answers questions, walks causal chains, and **verifies every citation against the database
> before you see it**. When Kenny can't ground an answer, it says so instead of guessing.

Three ideas carry the system:

1. **Everything is evidence.** Every stakeholder, decision, risk, and commitment traces back to source
   events in an append-only ledger (enforced by database trigger, not convention).
2. **The agent is accountable.** Citations are DB-verified per claim; cross-engagement leaks are hard-rejected
   and audited; side-effectful tool calls pause for human approval; an eval gate with a zero-leak requirement
   runs in CI.
3. **Humans stay in the loop.** Extractions, agent escalations, and citation disputes flow through a Review
   Inbox; resolved escalations become new canonical evidence, so answering a question once grounds every
   future answer.

---

## Quickstart

```bash
git clone https://github.com/kennygeiler/DeployAI.git && cd DeployAI
pnpm install --frozen-lockfile
cp infra/compose/.env.example infra/compose/.env       # add ANTHROPIC_API_KEY
make dev                                               # full local stack — first run 5-15 min
make seed-scenario-bluestate                           # 26-week ground-truth engagement
open http://localhost:3000/engagements
```

The stack is nine containers: web, control-plane, Postgres (pgvector + Apache AGE), Redis, MinIO,
Keycloak, embedder, MCP server, and a TSA stub. `make dev-verify` health-checks all of them.

Then:

1. Open **BlueState Health — Member Portal Replatform**.
2. Explore the matrix — every node carries provenance back to its source events; the snapshot slider
   replays past states.
3. Ask **Agent Kenny**: *"What concerns were raised before we approved the identity-provider decision?"*
   Kenny calls tools, walks the causal chain, and cites every claim inline. Ask it something the
   engagement doesn't contain and it will tell you that — with the nearest real matches — rather than
   invent an answer.
4. Open **Review** in the sidebar — the HITL inbox for extraction proposals, agent escalations, and
   citation disputes.
5. Visit `/admin/agent-kenny-dashboard` for hallucination rate, tool-call distribution, and latency
   percentiles.

Denser fixtures (seedable from the onboarding wizard or the internal API): **BlueState-XL** (5 years,
~2.5k ledger events, ~70 stakeholders — also the longscale eval corpus) and **Portfolio** (5 sibling
engagements, used to prove tenant/engagement isolation).

### Cloud deploy (Railway)

One Railway project, five services (postgres / control-plane / web / mcp-server / embedder) plus
managed Redis, each built from the repo root against its own Dockerfile
(`railway up --service <name>`), with CI auto-deploy on `main` gated on the test suite and volume
backups for Postgres. Hosted auth is currently a short-lived bootstrap JWT
(`scripts/cloud-token.sh`). Full operator runbook:
[`docs/ops/cloud-deploy.md`](./docs/ops/cloud-deploy.md).

---

## What's in the box

| Surface | What it does | Where it lives |
|---|---|---|
| **Engagement matrix** | Typed property graph — stakeholders / systems / decisions / risks / commitments — with per-node provenance and daily snapshots. Mirrored into an Apache AGE graph for Cypher traversal. | `apps/web/src/app/(strategist)/engagements/` |
| **Event ledger** | Append-only causal log (DB-trigger-enforced). Every state change emits a `ledger_event` with `caused_by` / `affects` edges — the backbone of audit, chain-walking, and provenance. | `services/control-plane/src/control_plane/ledger/` |
| **Agent Kenny** | Checkpointed LangGraph agent (Postgres saver, tenant-scoped threads): retrieve → reason → tool-call → verify citations → review → persist + audit. 13 read tools; the only write tool is `propose_action`. Runtime selectable (`DEPLOYAI_AGENT_RUNTIME=langgraph\|legacy`) with a CI parity gate between drivers. | `services/control-plane/src/control_plane/agents/agent_kenny/` |
| **Citation discipline** | Every `[event:UUID]` / `[node:UUID]` / `[insight:UUID]` in a reply is DB-checked against the current tenant + engagement — verified, revised, or flagged. A cross-engagement citation hard-rejects the reply and emits a security ledger event. | `agents/agent_kenny/nodes/citations.py` |
| **In-turn approvals** | Side-effectful tool calls (external MCP writes) pause the graph via `interrupt()`, stream an `approval_required` frame, and render an approval card in chat. Approve later — the checkpointed thread resumes exactly where it stopped. | `agents/agent_kenny/approvals.py`, `apps/web/src/components/ui/approval-card.tsx` |
| **Review Inbox (HITL)** | One queue for extraction proposals, agent escalations, and citation disputes. Resolving an escalation with an answer records it as canonical, cited evidence — the knowledge flywheel. Confidence-thresholded auto-accept with a deterministic sampling audit. | `services/control-plane/src/control_plane/services/review_inbox.py`, `apps/web/src/app/(strategist)/review/` |
| **Tenant isolation** | Postgres row-level security (FORCE) on every tenant-scoped table, per-tenant service tokens, a catalog test that fails CI if a new table ships without RLS, and a cross-tenant fuzz harness (10k attempts per run) with an anti-test proving the fuzzer catches real leaks. | `alembic/versions/`, `tests/fuzz/` |
| **MCP, both directions** | Inbound: a standalone read-only MCP server so Claude Desktop / IDEs can query the matrix + ledger with tenant API keys. Outbound: Kenny can call tenant-enabled connectors (Slack wired; others staged) behind four ordered guards — kill switch → allow-list → rate limit → SSRF egress guard. | `services/mcp-server/`, `agents/agent_kenny/mcp_client.py` |
| **Search** | Keyword + pgvector semantic search (`vector(1024)`, HNSW, Voyage-3 embeddings via a durable job queue) as tools available to Kenny and the UI. | `agents/tools/search.py`, migrations `0050` |
| **Eval harness** | 30 hand-curated golden questions grounded in the seeded corpus, run by a real CLI against a self-provisioned database. Blocking PR gate (deterministic 5-question subset), nightly sample + weekly full run, and an unconditional **cross-engagement-leak-count = 0** hard-fail. | `services/control-plane/tests/golden/agent_kenny/`, `.github/workflows/agent-kenny-eval.yml` |
| **Admin dashboard** | Hallucination rate, tool-call distribution, p50/p95/p99 latency, IDK rate, lint flags, top-cited events, adversarial concerns. | `apps/web/src/app/(strategist)/admin/agent-kenny-dashboard/` |

---

## Architecture

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  apps/web — Next.js 16 (App Router, React 19)                                 │
│  engagements · matrix + snapshots · timeline · Review Inbox · admin           │
│  Agent Kenny chat (SSE: thinking / tool chips / inline citations / approvals) │
│  OIDC login · edge authz middleware · Zod-validated BFF routes                │
└──────────────────────────────┬────────────────────────────────────────────────┘
                               │  BFF → internal API (per-tenant service tokens)
                               ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  services/control-plane — FastAPI + async SQLAlchemy                          │
│                                                                               │
│   Domain / API              Agent Kenny (LangGraph)      Workers              │
│   ────────────              ────────────────────────     ─────────            │
│   matrix · ledger           retrieve → llm_call →        synthesizer          │
│   review inbox · insights   tools → citations →          embedder (Voyage-3)  │
│   analyzers · auth/OIDC     review → persist+audit       lint                 │
│   service tokens            checkpointer · interrupt()                        │
└──────────────────────────────┬────────────────────────────────────────────────┘
                               │
          ┌────────────────────┼──────────────────────────┐
          ▼                    ▼                          ▼
┌──────────────────┐  ┌───────────────────┐  ┌────────────────────────────┐
│ Postgres 16      │  │ services/         │  │ Outbound MCP (per tenant)  │
│ RLS (FORCE) on   │  │ mcp-server        │  │ kill switch → allow-list → │
│ all tenant data  │  │ inbound MCP,      │  │ rate limit → egress guard  │
│ pgvector · AGE   │  │ read-only,        │  │ (Slack wired)              │
│ agent checkpoints│  │ tenant API keys   │  │                            │
└──────────────────┘  └───────────────────┘  └────────────────────────────┘
     Redis (rate limits, sessions) · MinIO (artifacts) · Anthropic Claude
     (Sonnet 5 default) · Voyage-3 embeddings
```

Why the substrate is shaped this way: [`docs/agent-kenny/ethos.md`](./docs/agent-kenny/ethos.md) —
the ledger is the wiki, Kenny is its disciplined librarian, every claim cites its source.

---

## Testing & quality gates

- **~2,000 tests**: 800+ control-plane unit + ~600 integration (real Postgres testcontainers, Alembic to
  head), ~570 web (vitest + RTL), plus contract, authz, tenancy, provider, and MCP-server suites.
- **Runtime parity gate** — key agent integration suites run against *both* drivers; a golden-question
  parity test gates the LangGraph cutover.
- **Cross-tenant fuzz** — 10,000 attack attempts per CI run across 20 tables, with an anti-test that
  disables RLS and asserts the harness catches the leak.
- **Eval gates** — blocking PR gate on a deterministic golden subset; nightly/weekly LLM evals with an
  unconditional zero-cross-engagement-leak requirement.
- **Static gates** — mypy strict, ruff, TypeScript strict, eslint, prettier, WCAG-AA-asserted design
  tokens, axe/pa11y a11y checks, SHA-pinned actions, SBOM + CVE scan (Critical blocks).

```bash
# Reproduce the CI gate locally
pnpm turbo run lint typecheck test build && pnpm -w run format:check
cd services/control-plane && uv run mypy && uv run pytest tests/unit
```

---

## Production hardening

Reliability and governance are built in, not aspirational — each mechanism links to the code that
implements it and the doc or test that proves it:

| Concern | Mechanism |
|---|---|
| **Idempotency** | Canonical-event writes are [idempotent inserts](./services/control-plane/src/control_plane/infra/canonical_idempotent_write.py) keyed by dedup key; the XL scenario generator is uuid5-deterministic; re-running extraction on an event returns the same proposals without a second LLM call (pinned by [latency/idempotency tests](./services/control-plane/tests/integration/test_demo_capture_latency.py)) |
| **Retry** | Provider-level [backoff + full jitter](./packages/llm-provider-py/src/llm_provider_py/util.py) on 429/5xx/529 and transport errors, `Retry-After` honored; streaming requests retry only until the first chunk is delivered — a partial stream is never replayed |
| **Rate limiting** | Inbound [per-principal token bucket](./services/control-plane/src/control_plane/infra/rate_limit.py) (Redis-backed or in-memory, [docs](./docs/ops/rate-limiting.md)), outbound MCP rate limiter, and per-tenant daily LLM token budgets charged *before* the turn |
| **Role scoping** | OIDC → control-plane-minted RS256 JWTs, a [role/action matrix](./packages/authz) with TS + Python twins, per-tenant service tokens, RLS `FORCE`'d on all tenant tables, and a read-only `demo_guest` role for the public demo |
| **Distributed tracing** | [OpenTelemetry spans](./services/control-plane/src/control_plane/infra/tracing.py) from the web BFF through the control plane to LLM, tool, and MCP calls (W3C `traceparent` end to end); `trace_id` joins `request_id` in every structured log line ([docs](./docs/ops/tracing.md)) |
| **Self-healing** | [Circuit breakers](./services/control-plane/src/control_plane/infra/circuit_breaker.py) per MCP connector and on the embedder (half-open probes, automatic recovery); checkpointed agent turns [resume across process death](./services/control-plane/tests/integration/test_agent_durability.py); salvage paths keep turns legible (synthesized tool results, final answer after tool-cap, zero-citation revision). Fail-open/fail-closed policy per dependency: [docs/ops/resilience.md](./docs/ops/resilience.md) |
| **Policy as code** | The CI gates *are* the policy engine: an unconditional cross-engagement leak gate, an RLS catalog test (a new tenant table without a policy fails the build), WCAG-AA-asserted design tokens, SHA-pinned actions, SBOM + CVE scanning with Criticals blocking, and a [zero-secret daily canary](./.github/workflows/prod-canary.yml) against production |
| **Compliance trail** | Ledger is append-only **by database trigger**; every guard denial writes a distinct audit kind; CVE triage decisions are [recorded with dispositions](./docs/security/) awaiting human sign-off |

---

## Tech stack

| Layer | Tooling |
|---|---|
| Frontend | Next.js 16 (App Router, React 19), TypeScript strict, Tailwind v4, design-token system (light + dark, WCAG AA enforced by tests), Zod at every boundary |
| Backend | FastAPI, async SQLAlchemy 2.x, Alembic, Pydantic v2, `uv`, ruff + mypy strict |
| Database | Postgres 16 + pgvector (HNSW) + Apache AGE (Cypher graph mirror), row-level security FORCE'd on tenant data |
| Agent runtime | LangGraph StateGraph + Postgres checkpointer (`AsyncPostgresSaver`), `interrupt()` approvals; direct Anthropic Messages API for streaming tool-use (no LangChain) |
| LLM | Anthropic Claude (Sonnet 5 default, per-tenant configurable) · Voyage-3 1024-dim embeddings |
| Agent protocol | MCP — inbound read-only server + guarded outbound client |
| Auth | OIDC (PKCE) with control-plane-minted RS256 session JWTs; per-tenant internal service tokens |
| Infra | docker-compose locally (`make dev`); Railway in the cloud (5 services + managed Redis, CI-gated auto-deploy, volume backups) |
| Monorepo | pnpm workspaces + Turborepo (TS) · uv per Python service |

---

## Repository layout

| Path | Role |
|---|---|
| `apps/web/` | Next.js app — engagements, matrix, timeline, chat, Review Inbox, admin, BFF routes |
| `services/control-plane/` | FastAPI core — domain, ledger, Agent Kenny, Review Inbox, workers, analyzers, auth, migrations |
| `services/mcp-server/` | Standalone read-only MCP protocol server (tenant API keys) |
| `services/_shared/` | Shared Python libs — authz, tenancy (RLS sessions), citation envelope, ingest helpers |
| `packages/llm-provider-py/` | LLM provider protocol — Anthropic (streaming + native tool-use, sync/async), OpenAI, stub |
| `packages/authz/` · `packages/contracts/` · `packages/design-tokens/` | Role/action matrix (TS + Python twins) · cross-workspace schemas · design system |
| `infra/compose/` | Local stack + seed scenarios (BlueState, BlueState-XL, Portfolio) — the Postgres image here (pgvector + Apache AGE) is also what Railway builds |
| `infra/archive/fly/` | Superseded Fly.io configs, kept as history (cloud deploy is Railway; no per-service config files needed) |
| `docs/` | Start at [`docs/agent-kenny/INDEX.md`](./docs/agent-kenny/INDEX.md); superseded material in `docs/archive/` |

---

## Where to find more

- [`docs/engineering-highlights.md`](./docs/engineering-highlights.md) — every engineering claim mapped to the code and CI gate that proves it
- [`docs/agent-kenny/ethos.md`](./docs/agent-kenny/ethos.md) — architectural rationale (the load-bearing doc)
- [`docs/agent-kenny/eval.md`](./docs/agent-kenny/eval.md) — the golden-question harness, CLI, and CI cadence
- [`docs/security/`](./docs/security/) — tenant-isolation model, MCP outbound threat model, cross-tenant fuzz harness
- [`docs/ops/cloud-deploy.md`](./docs/ops/cloud-deploy.md) — Railway operator runbook · [`docs/ops/backup.md`](./docs/ops/backup.md) — backup/restore, local + cloud
- [`docs/dev-environment.md`](./docs/dev-environment.md) — toolchains and workflows

---

## License

UNLICENSED — see [`package.json`](./package.json) `license` field.
