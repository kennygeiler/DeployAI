# DeployAI

[![Node](https://img.shields.io/badge/node-24.x-339933?logo=nodedotjs)](./.nvmrc)
[![pnpm](https://img.shields.io/badge/pnpm-workspace-f69220?logo=pnpm)](./pnpm-workspace.yaml)
[![Turbo](https://img.shields.io/badge/build-turbo-000000?logo=turborepo)](./turbo.json)
[![Python](https://img.shields.io/badge/python-3.13-3776AB?logo=python)](./services/control-plane/.python-version)
[![License](https://img.shields.io/badge/license-UNLICENSED-lightgrey.svg)](./README.md#license)

> **Customer-deployment co-pilot.** Capture every email, meeting note, and decision across a long-cycle deployment → build a typed property graph of stakeholders / systems / decisions / risks → surface insights and chat with **Mr. Oracle** about any of it.

---

## TL;DR

```bash
git clone https://github.com/kennygeiler/DeployAI.git && cd DeployAI
pnpm install --frozen-lockfile
cp infra/compose/.env.example infra/compose/.env   # add ANTHROPIC_API_KEY
make dev                                            # full local stack
make seed-scenario-bluestate                        # ground-truth 26-week demo
open http://localhost:3000/engagements
```

Click **BlueState Health — Member Portal Replatform** → scrub the matrix time-slider, ask **Mr. Oracle** a question, drag the date filter on any section.

---

## What it does

| | |
|---|---|
| **Captures** | Email pastes, meeting transcripts, manual notes — parsed and stored as canonical events |
| **Extracts** | LLM agent (Cartographer) builds a typed graph: stakeholders, systems, decisions, risks, commitments, opportunities |
| **Reviews** | Proposals dedup-grouped; one-click accept/reject; audit-the-AI rejection feeds back |
| **Maps** | Time-travelable property graph — drag the slider to see any historical state |
| **Surfaces** | 6 deterministic analyzers (engagement silence, decision-cycle slowdown, risk-open rate, stakeholder churn, extractor drift, decision provenance) |
| **Audits** | Append-only ledger with causal-chain edges — every claim cites its source events |
| **Chats** | **Mr. Oracle** side panel — grounded in the engagement's full ledger + matrix; cites events and nodes inline |

---

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  apps/web (Next.js 16, App Router)                                  │
│  /engagements  /engagements/[id]  /engagements/[id]/timeline        │
│   • Matrix graph view + time slider     • Mr. Oracle chat panel     │
│   • Per-section date-range filters      • Audit-AI reject flow      │
└──────────────────────────────────┬──────────────────────────────────┘
                                   │ BFF routes (Next.js server)
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  services/control-plane (FastAPI + async SQLAlchemy 2.x)            │
│   • Ingest → Cartographer (LLM extraction agent)                    │
│   • Ledger emitter (dual-emit on every state change)                │
│   • Oracle chat service + 6 statistical analyzers                   │
│   • Matrix CRUD + snapshots + causal-chain walker                   │
│   • Per-tenant LLM budget (daily token cap)                         │
└──────────────────────────────────┬──────────────────────────────────┘
                                   ▼
┌────────────────────────────────────────────────────────────────────┐
│  Postgres 16 + pgvector  •  Redis  •  MinIO (S3-compatible)         │
└────────────────────────────────────────────────────────────────────┘
```

---

## Repository layout

| Path | Role |
|---|---|
| `apps/web/` | Next.js — engagement portfolio, detail, timeline, Mr. Oracle panel, BFF routes |
| `services/control-plane/` | FastAPI — domain, internal APIs, agents, ledger, analyzers, snapshots |
| `packages/llm-provider-py/` | `LLMProvider` protocol + Anthropic / OpenAI / stub impls; streaming via `chat_complete_stream` |
| `packages/authz/` | TS + Python role/action matrix (shared) |
| `packages/contracts/` `packages/design-tokens/` `packages/shared-ui/` | Cross-workspace types + design system |
| `infra/compose/` | Reference local stack + `seed_app.py` (smoke) + `seed_scenario_bluestate.py` (26-week ground-truth) |
| `docs/` | Product spec (`docs/product/deployai-source-of-truth-spec.md`), design records, test scenarios |
| `briefs/` | Sub-agent spawn briefs (gitignored working artifacts; see `AGENTS.md`) |

---

## Features by phase

**Phase 1–7 (MVP loop)** — paste / extract / review / matrix / per-engagement Oracle insights / portfolio-level Master Strategist insights.

**Phase F (timeline ledger)** — append-only ledger with `caused_by` + `affects` edges. Matrix time-slider over daily snapshots. Provenance drawer on any node. 6 statistical analyzers + LLM-narrated `decision_provenance_summary`. Per-tenant LLM budget. Sales pitch: "audit any decision back to source evidence" — compliance-buyer ready.

**Phase G (post-F polish + Mr. Oracle)** — chat panel grounded in engagement state (dual-emits every reply to the ledger; conversations themselves auditable). Member-by-email auto-provision. Inline node edit dialog. Audit-AI reject flow. Insight grouping by severity. Per-section date filters. Edge colors by type. Colorblind-safe palette. Per-stakeholder timeline filter. Recent-activity strip.

See [`docs/design/post-f-polish.md`](./docs/design/post-f-polish.md) for the post-F design pass.

---

## What's not built yet

- **OAuth ingestion** (Gmail, MS Graph, Otter API). Paste-only today; the BlueState seed shows the eventual shape.
- **Admin UI for LLM config.** Provider + key + model live in `infra/compose/.env`.
- **Onboarding wizard** for an empty database — exists for the simple seed; not wired into the BlueState scenario.
- **Pilot / production hardening** — TLS, SSO/SAML, secret rotation, runbooks. The `docs/pilot/` pack predates the pivot; usable as a reference.
- **Temporal-insights UI surface** — analyzer-produced insights have a backend snooze endpoint but no dedicated list page yet (legacy MatrixInsight surface still owns the UI).

---

## Configuration

| Topic | Where |
|---|---|
| Local stack env | [`infra/compose/.env.example`](./infra/compose/.env.example) — Postgres / Redis / MinIO / CP URLs + LLM key |
| Dev role injection | `apps/web/middleware.ts` — `DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1` (set by compose) auto-injects `x-deployai-role` + tenant. **Never** set in a hosted deploy |
| Pilot session + headers | [`docs/pilot/session-and-headers.md`](./docs/pilot/session-and-headers.md) — `DEPLOYAI_WEB_TRUST_JWT`, PEM, issuer/audience |
| Seed customization | [`infra/compose/seed/README.md`](./infra/compose/seed/README.md) |

Production secrets belong in a vault, not in `.env`.

---

## Verifying a clean checkout

```bash
pnpm install --frozen-lockfile
pnpm turbo run lint typecheck test build    # full CI gate
pnpm -w run format:check                    # prettier (CI catches this independently)
```

The repo's CI runs the same plus compose-smoke, canonical-memory-schema, cross-tenant fuzz, CVE scan, and SBOM generation.

---

## Documentation

| Document | Audience | Purpose |
|---|---|---|
| [`docs/product/deployai-source-of-truth-spec.md`](./docs/product/deployai-source-of-truth-spec.md) | Everyone | Canonical product intent + §16 phased roadmap. **Start here.** |
| [`docs/design/timeline-ledger.md`](./docs/design/timeline-ledger.md) | Engineers | Phase F design: ledger, snapshots, analyzers, provenance |
| [`docs/design/post-f-polish.md`](./docs/design/post-f-polish.md) | Engineers | Phase G design: Mr. Oracle + UX bundles G0–G4 |
| [`docs/test-scenarios/bluestate-health.md`](./docs/test-scenarios/bluestate-health.md) | Owners + Eng | Ground-truth doc for `make seed-scenario-bluestate` — what to expect on screen |
| [`AGENTS.md`](./AGENTS.md) | Sub-agents | Binding rules for parallel sub-agent work |
| [`ORCHESTRATOR.md`](./ORCHESTRATOR.md) | Main thread | Autonomy contract + concurrency policy |
| [`docs/product/synthesis-agents.md`](./docs/product/synthesis-agents.md) | Engineers | Oracle + Master Strategist design (Phase 7.1) |
| [`docs/product/matrix-extraction-agent.md`](./docs/product/matrix-extraction-agent.md) | Engineers | Cartographer design (Phase 6.2b) |
| [`docs/dev-environment.md`](./docs/dev-environment.md) | Engineers | Toolchains, pnpm workflows, compose stack |

---

## Maturity

End-to-end demo on real data via the BlueState Health 26-week seed. All Phase F + G surfaces shipped + CI green. No paying customers yet — the next milestone is sitting next to a real deployment strategist with their own engagement data.

---

## License

UNLICENSED — see [`package.json`](./package.json) `license` field.
