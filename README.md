# DeployAI

[![Node](https://img.shields.io/badge/node-24.x-339933?logo=nodedotjs)](./.nvmrc)
[![pnpm](https://img.shields.io/badge/pnpm-workspace-f69220?logo=pnpm)](./pnpm-workspace.yaml)
[![Turbo](https://img.shields.io/badge/build-turbo-000000?logo=turborepo)](./turbo.json)
[![License](https://img.shields.io/badge/license-UNLICENSED-lightgrey.svg)](./README.md#license)

**A team-based engagement tracker for cross-functional deployment teams**, built on a
canonical-memory substrate. DeployAI gives a team running many long-cycle customer
deployments — a forward-deployed engineer, a deployment strategist, a biz-dev lead — one
place to track each engagement, capture what happened, and see it through every role's lens.

> **Maturity: prototype.** This is a well-engineered **prototype skeleton**, not a finished
> product — **demo-usable**, not pilot- or production-ready. The codebase was generated with
> the BMAD method and has since been pivoted toward team-based engagement tracking (Phases
> 0–4, below). Before trusting any "done" label anywhere in the repo, read the **single
> source of truth**: [`docs/product/deployai-source-of-truth-spec.md`](./docs/product/deployai-source-of-truth-spec.md).

---

## What DeployAI is

DeployAI began as a single-strategist *deployment system of record* — durable, cited memory
for long-cycle, high-stakes customer deployments. It has been **pivoted into a team tool**:
a cross-functional team tracking *many* engagements and finding insight across them.

- **Tenant = the team.** **Engagement = one customer deployment** that team runs.
- Each engagement carries its deployment phase, its members (with team roles), and a log of
  meetings / decisions / risks / next-actions.
- The two product shapes share the **canonical-memory substrate** (event log, identity
  graph, evidence) and little else; the older single-strategist surfaces remain in the repo
  as demo-grade scaffolding.

Product intent, architecture, honest real-vs-fixture status, and the phased roadmap that
drives the pivot all live in the source-of-truth spec — **§16 is the live roadmap and the
handoff point** for anyone continuing the work.

---

## Is this codebase right for you?

**A good fit if you are:**

- An **engineering team** that wants a clean, typed, well-tested starting point for a
  team-based deployment/engagement tracker and intends to **own and extend it**.
- A **stakeholder evaluating the architecture** — a polyglot monorepo with a
  canonical-memory data model, tenant isolation, a control-plane / BFF boundary, async
  migrations, and agent-evaluation contracts.

**It is not:**

- A turnkey or hosted SaaS product — you run and operate it yourself.
- Pilot- or production-ready out of the box — see the demo / pilot / production staging in
  spec §13.
- An "AI agent" product *today* — the agentic layer is deterministic heuristics. There is
  no live LLM loop ingesting meetings and updating surfaces (that is Phase 5, not started).

**How to evaluate it:** run the [Quick start](#quick-start), walk the `/engagements`
surfaces, then read spec **§3** (honest maturity) and **§13** (demo vs pilot vs production).
[`_bmad-output/implementation-artifacts/sprint-status.yaml`](./_bmad-output/implementation-artifacts/sprint-status.yaml)
is the code-verified delivery tracker.

---

## What works today

The team-tracking pivot is delivered through **Phase 4** — all on real Postgres data via the
control plane:

- **Engagement portfolio** (`/engagements`) — every customer deployment for the team, with
  its phase and status.
- **Engagement detail** (`/engagements/[id]`) — one deployment with its team, its log, and a
  cross-role activity breakdown.
- **Team & roles** — assign / remove forward-deployed-engineer, deployment-strategist, and
  biz-dev members on an engagement; roles flow through real JWT/session auth and the authz
  matrix (TypeScript + Python).
- **Manual capture** — log meeting / decision / risk / next-action notes against an
  engagement, with server-derived author attribution and team-role tagging.
- **Role lenses** — filter an engagement's log by author role; a deterministic breakdown
  surfaces where a role has not weighed in.
- **Strategist queues** — action / validation / solidification queues, engagement-scoped and
  Postgres-backed via the control plane.
- **Control plane** — FastAPI + async SQLAlchemy + Alembic migrations, internal APIs, tenant
  isolation; brought up by a one-command Docker Compose stack.

## What's not built yet

- **Phase 5 — Intelligence** (not started): the agent loop, M365 ingestion, meeting
  presence, and insight *synthesis*. Cross-role "insight" today is deterministic counts —
  not semantic divergence detection.
- The **older single-strategist surfaces** (morning digest, evening synthesis, in-meeting
  alert) remain **fixture / demo-grade**.
- **Deferred plumbing** — the canonical-memory `engagement_id` retrofit; the engagement
  selector is currently action-queue-only. See spec §16 for the full deferred list.
- **No production/pilot hardening** beyond the pilot operator pack.

---

## Quick start

**Prerequisites:** **Node 24.x** and **pnpm 10.x** (see root `package.json` `engines` and
[.nvmrc](./.nvmrc)); `pnpm` refuses unsupported Node majors.

```bash
git clone https://github.com/kennygeiler/DeployAI.git
cd DeployAI
pnpm install --frozen-lockfile
pnpm --filter @deployai/web dev
```

The web app serves on **http://localhost:3000** — start at **`/engagements`**, the team's
engagement portfolio.

**Development-only role injection:** in `NODE_ENV=development`,
[`apps/web/middleware.ts`](./apps/web/middleware.ts) injects `x-deployai-role:
deployment_strategist` when headers are missing so strategist/engagement APIs do not 401 in
local dev. Set `DEPLOYAI_DEV_STRATEGIST_ROLE` to try the `fde` or `biz_dev` lenses, or
`DEPLOYAI_DISABLE_DEV_STRATEGIST=1` to turn injection off. Full behavior is in
[docs/dev-environment.md](./docs/dev-environment.md).

**Full local stack** (Postgres, Redis, MinIO, control plane, seeded web) — engagement
surfaces need this for live data: from the repo root, `make dev` then `make dev-verify`
([docs/dev-environment.md §7](./docs/dev-environment.md#7-local-stack-via-docker-compose-story-17)).

**CI-style verification** on a clean machine: `pnpm turbo run lint typecheck test build`.

---

## Architecture & repository layout

DeployAI is a polyglot monorepo — **pnpm + Turborepo** orchestrate Node, Python (`uv`), Go,
and Rust workspaces. CI runs lint, typecheck, unit tests, accessibility gates, compose
smoke, SBOM/CVE scanning, and cross-tenant isolation fuzz.

| Path | What it is |
| --- | --- |
| `apps/web` | Next.js (App Router) — engagement + strategist surfaces, BFF route handlers, Vitest tests. |
| `services/control-plane` | FastAPI + async SQLAlchemy 2.x + Alembic — internal APIs, the Postgres data plane. |
| `services/` (ingest, cartographer, oracle, master_strategist) | Ingestion and the three agents — deterministic Python heuristics today; no live LLM loop. |
| `packages/` | Design tokens, contracts, `shared-ui`, `@deployai/authz` (TS) + `deployai_authz` (Python). |
| `apps/edge-agent` | Tauri desktop capture agent (Rust + Vite frontend). |
| `apps/foia-cli` | Go CLI for FOIA-oriented export workflows. |
| `infra/compose` | Docker Compose reference stack and seed data. |
| `docs/` | Engineering and hosted-pilot documentation. |
| `_bmad-output/` | BMAD planning artifacts and the code-verified delivery tracker. |

More detail: [docs/repo-layout.md](./docs/repo-layout.md).

---

## Configuration & deployment

| Topic | Where to start |
| --- | --- |
| **Env template & variables** | [.env.example](./.env.example) — control-plane URLs, internal keys, OIDC placeholders, strategist/pilot web vars. |
| **JWT, tenant & header boundaries** | [docs/pilot/session-and-headers.md](./docs/pilot/session-and-headers.md) — `DEPLOYAI_WEB_TRUST_JWT`, PEM, issuer/audience, `DEPLOYAI_STRATEGIST_REQUIRE_TENANT`. |
| **Hosted pilot operator pack** | [docs/pilot/README.md](./docs/pilot/README.md) — sessions, loaders, queues, runbooks. |
| **Hardening checklist** | [docs/pilot/hosted-environment.md](./docs/pilot/hosted-environment.md) — TLS, control-plane coupling, loaders. |
| **Pre–external-visitor checklist** | [docs/pilot/phase-0-checklist.md](./docs/pilot/phase-0-checklist.md). |
| **Demo vs pilot vs production** | [source-of-truth spec §13](./docs/product/deployai-source-of-truth-spec.md). |

Production and pilot deployments should source **secrets from a vault**, not committed
`.env` files, and align web/control-plane URLs, keys, and JWT trust material per the pilot
docs above.

---

## Documentation

| Document | Audience | Purpose |
| --- | --- | --- |
| [docs/product/deployai-source-of-truth-spec.md](./docs/product/deployai-source-of-truth-spec.md) | Everyone | **Canonical source of truth** — product intent, architecture, honest status, and the §16 phased roadmap. Start here. |
| [docs/dev-environment.md](./docs/dev-environment.md) | Engineers | Toolchains, `pnpm` workflows, dev middleware, the compose stack, smoke commands. |
| [docs/repo-layout.md](./docs/repo-layout.md) | Engineers | Detailed workspace map. |
| [docs/pilot/README.md](./docs/pilot/README.md) | Hosted-pilot operators | Index of pilot runbooks and env bundles. |
| [_bmad-output/implementation-artifacts/sprint-status.yaml](./_bmad-output/implementation-artifacts/sprint-status.yaml) | Engineering | Delivery tracker — honest, code-verified status. |

Supporting references: [docs/human-ops-runbook.md](./docs/human-ops-runbook.md) (secrets,
CI, release operations), [.github/workflows/README.md](./.github/workflows/README.md)
(automation overview).

---

## License

UNLICENSED — see the [`package.json`](./package.json) `license` field.
