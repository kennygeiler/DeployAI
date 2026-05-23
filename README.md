# DeployAI

[![Node](https://img.shields.io/badge/node-24.x-339933?logo=nodedotjs)](./.nvmrc)
[![pnpm](https://img.shields.io/badge/pnpm-workspace-f69220?logo=pnpm)](./pnpm-workspace.yaml)
[![Turbo](https://img.shields.io/badge/build-turbo-000000?logo=turborepo)](./turbo.json)
[![License](https://img.shields.io/badge/license-UNLICENSED-lightgrey.svg)](./README.md#license)

**Deployment-matrix and cross-team-insight platform for cross-functional deployment teams.**
DeployAI captures every interaction on a long-cycle customer deployment — email, meeting
notes, field notes, manual entry — builds a typed property graph of stakeholders / systems
/ decisions / risks / commitments / opportunities, and produces cited insight on top of
that graph at both the per-engagement and the cross-engagement (portfolio) level.

> **Maturity: MVP-shipped, evaluation phase.** The full ingest → extract → review → matrix
> → per-engagement insight → cross-engagement insight loop runs end to end on real data.
> No paying customers yet — the next milestone is sitting beside a real deployment
> strategist and running them through the loop with their own model keys. See the **single
> source of truth**: [`docs/product/deployai-source-of-truth-spec.md`](./docs/product/deployai-source-of-truth-spec.md).

---

## What DeployAI is

A team of forward-deployed engineers, deployment strategists, and biz-dev leads is the
**tenant**. Each customer deployment they run is an **engagement**. Within an engagement
the platform:

1. **Ingests** what happened — paste an email or a meeting transcript on the engagement
   page; the parser extracts headers / participants / dates and stores the body as a
   canonical event. Plain-text and JSON one-shots also accepted.
2. **Extracts** matrix entities via the Cartographer agent — reads each canonical event
   plus the engagement's current matrix and proposes typed nodes (stakeholder,
   organization, system, decision, risk, commitment, opportunity) and edges (sponsors,
   owns, blocks, threatens, depends_on, etc.).
3. **Reviews** in the UI — proposals collapse by `(kind, summary)` so duplicate
   extractions for the same stakeholder become one card; the strategist accepts /
   rejects, with a "Accept (dedup)" shortcut that picks the first and dismisses the rest.
4. **Maps** the accepted entities into the typed property graph stored alongside the
   canonical-memory substrate, with every node citing the events that evidence it.
5. **Surfaces per-engagement insight** via the Oracle agent — deterministic predicates
   flag stale commitments, unanswered risks, decisions without owners, and stakeholder
   neglect, then a single LLM call phrases each one. One refresh, ~$0.05 in tokens.
6. **Surfaces cross-engagement insight** via the Master Strategist agent — recurring
   risk patterns across engagements, system concentration, role-coverage gaps. Same
   on-demand refresh pattern at the portfolio (`/engagements`) level.

The full loop, end to end. Phase 7.5 onwards (matrix graph viz, OAuth ingestion harnesses,
admin-UI LLM config, prompt tuning) is deferred until customer testing decides what
matters first.

---

## Is this codebase right for you?

**A good fit if you are:**

- A **team running customer deployments** (FDE / deployment strategist / biz-dev) who
  wants to **run and modify the platform yourself**, against your own model keys, on your
  own infrastructure. DeployAI is sold as a base your engineers tailor; not a hosted SaaS.
- An **engineering team** evaluating a polyglot monorepo (TS + Python + a few packages)
  with a clean canonical-memory data model, async-SQLAlchemy + Alembic migrations,
  retrieval-bound LLM agents under a Protocol seam, and tenant isolation.

**It is not:**

- A turnkey hosted product. You operate it. You bring keys.
- Pilot- or production-hardened. The MVP loop works end to end; OAuth, multi-tenant
  isolation hardening, an admin UI for model config, and onboarding wizards are all
  TODO. See **What's not built yet** below.

**How to evaluate it:** run the [Quick start](#quick-start), seed the demo data
(`make seed-app`), open `/engagements`, click **Refresh portfolio insights**, then open
either of the two seeded engagements and click **Refresh insights**. That's the product.

---

## What works today (MVP loop)

All on real Postgres data via the control plane; all tested under `pnpm turbo run lint
typecheck test build`:

- **Engagement portfolio** (`/engagements`) — every customer deployment for the team,
  with its phase and status, **plus** the Master Strategist's cross-engagement insights at
  the top (recurring risk patterns, system concentration, role-coverage gaps).
- **Engagement detail** (`/engagements/[id]`) — one deployment with its team, the deployment
  matrix (typed property graph), pending Cartographer proposals (dedup-grouped, kind /
  type filterable, bulk-accept), and the Oracle's per-engagement insights.
- **Ingest harnesses** — universal JSON one-shot, **email paste** (RFC-822-ish header
  extraction), **meeting-notes paste** (Otter / Granola / plain-text detection).
- **Cartographer extraction agent** (`services/control-plane/src/control_plane/agents/matrix_extractor.py`)
  — chained from ingest, idempotent per event, dependency-injected LLM, stub fallback for
  no-key dev.
- **Oracle insight agent** (`agents/oracle.py`) — 4 insight types over the engagement
  matrix; predicates + one LLM call, dedup-key upsert idempotency, auto-resolve when the
  predicate stops firing.
- **Master Strategist** (`agents/master_strategist.py`) — 3 cross-engagement insight types
  via Jaccard title-family matching; same idempotency contract.
- **Team / role / membership** — tenant + users + engagement members across FDE,
  deployment strategist, biz-dev. Roles flow through the (TS + Python) authz matrix; dev
  mode injects a default role + tenant header.
- **Control plane** — FastAPI + async SQLAlchemy + Alembic + Anthropic LLM provider.
- **Repeatable seed** — `make seed-app` provisions a tenant, two engagements, ~28 events,
  and triggers Cartographer extraction so the demo state is ready in ~30 seconds and ~$1
  in tokens.

---

## What's not built yet

The MVP loop is the floor. None of these block the customer-test milestone, but each is
worth scoping based on what real testing surfaces:

- **OAuth ingestion harnesses** (Gmail, MS Graph, Otter API) — paste-only today.
- **Matrix graph visualization** — the matrix renders as a typed-and-grouped list, not a
  visual graph. List works at ~50 nodes; a graph view helps past that.
- **Admin UI for LLM config** — provider + key + model live in `infra/compose/.env`. A
  customer running this self-hosted edits a file and restarts the stack; a settings UI
  would be friendlier.
- **First-run onboarding wizard** — when the database is empty, `/engagements` could walk
  a customer through tenant naming, model selection, and first-engagement creation. Today
  it shows an empty list and requires running `make seed-app` or the CP internal API.
- **Pilot / production hardening** — TLS, SSO, secret rotation, runbooks. There's a pilot
  operator pack under `docs/pilot/` but it predates the pivot.

The §16 roadmap in the spec tracks scope; PRs #114–125 are the MVP delivery trail.

---

## Quick start

**Prerequisites:** **Node 24.x** + **pnpm 10.x** (`engines` in root `package.json`,
[.nvmrc](./.nvmrc)), **Docker** + **docker compose**, an **Anthropic API key** for real
LLM extraction (a stub provider runs in dev without one — predicates fire but the LLM
phrases nothing).

```bash
git clone https://github.com/kennygeiler/DeployAI.git
cd DeployAI
pnpm install --frozen-lockfile

# Configure your LLM key:
cp infra/compose/.env.example infra/compose/.env
# Then edit infra/compose/.env to add:
#   DEPLOYAI_LLM_PROVIDER=anthropic
#   ANTHROPIC_API_KEY=sk-ant-...

# Bring the stack up + seed:
make dev          # postgres, redis, minio, freetsa-stub, control-plane, web
make seed-app     # seed two demo engagements; chains Cartographer extraction (~$1)

# Open:
open http://localhost:3000/engagements
```

Click **Refresh portfolio insights** on the portfolio page. Open either engagement,
**Refresh insights**, accept a handful of proposals from the Proposals section, refresh
again — the matrix grows, insights tighten.

**CI-style verification on a clean checkout:** `pnpm turbo run lint typecheck test build`.

For browser testing without compose: `pnpm --filter @deployai/web dev` (no live data — UI
shell only). The dev middleware injects a default role + tenant header so strategist
surfaces don't 401.

---

## Architecture & repository layout

DeployAI is a polyglot monorepo orchestrated by **pnpm + Turborepo**. CI runs lint,
typecheck, unit tests, accessibility gates, compose smoke, SBOM/CVE scanning, and
cross-tenant isolation fuzz.

| Path | What it is |
| --- | --- |
| `apps/web/` | Next.js (App Router) — `/engagements` portfolio + detail, BFF route handlers, paste parsers, vitest tests. **The only customer-visible UI.** |
| `services/control-plane/` | FastAPI + async SQLAlchemy 2.x + Alembic — internal APIs, matrix domain models, the three synthesis agents (`agents/matrix_extractor.py`, `agents/oracle.py`, `agents/master_strategist.py`), Postgres data plane. |
| `packages/authz/` | Shared role + action matrix in TypeScript and Python. |
| `packages/llm-provider-py/` | `LLMProvider` protocol + `AnthropicProvider` + stub. Dependency-injected into the agents. |
| `packages/contracts/`, `packages/design-tokens/`, `packages/shared-ui/` | Cross-workspace types + design system. |
| `infra/compose/` | Docker Compose reference stack + `seed_app.py` + `seed/README.md`. |
| `docs/` | Engineering docs + product spec (`docs/product/deployai-source-of-truth-spec.md`). |

**Workspaces deferred for cleanup** (not part of the MVP loop, scheduled for retirement
in a follow-up cleanup pass): `apps/{edge-agent, eval, foia-cli, tools}`,
`packages/{foia-verifier, llama-citation-adapter, llm-provider}` (the TS variant —
`llm-provider-py` is the live one), `services/{_shared, config, cartographer, oracle,
master_strategist}` (those standalone services are pre-pivot; the live agents live in
`control-plane/src/control_plane/agents/`).

More detail: [docs/repo-layout.md](./docs/repo-layout.md) — note: that doc still lists the
deferred workspaces above; it is being updated.

---

## Configuration

| Topic | Where to start |
| --- | --- |
| **Local stack env** | [infra/compose/.env.example](./infra/compose/.env.example) — postgres / redis / minio / control-plane URLs + the LLM key. Copy to `.env` and set `ANTHROPIC_API_KEY` + `DEPLOYAI_LLM_PROVIDER=anthropic` for real extraction. |
| **Dev role + tenant injection** | `apps/web/middleware.ts` — `DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1` (set by compose) auto-injects `x-deployai-role: deployment_strategist` + a default tenant so dev/test traffic doesn't 401. Never set this in a hosted deploy. |
| **JWT / SSO** | [docs/pilot/session-and-headers.md](./docs/pilot/session-and-headers.md) — `DEPLOYAI_WEB_TRUST_JWT`, PEM, issuer/audience, `DEPLOYAI_STRATEGIST_REQUIRE_TENANT`. Pre-pivot; usable as a starting point for self-hosted hardening. |
| **Seed customization** | [infra/compose/seed/README.md](./infra/compose/seed/README.md) — `make seed-app SEED_APP_ARGS=...` for force-refresh, skip-extract. |

Production / pilot deployments should source **secrets from a vault**, not committed
`.env` files. The pilot doc set under `docs/pilot/` is from the pre-pivot era and is being
audited for what survives — for now, treat it as design reference rather than runbook.

---

## Documentation

| Document | Audience | Purpose |
| --- | --- | --- |
| [docs/product/deployai-source-of-truth-spec.md](./docs/product/deployai-source-of-truth-spec.md) | Everyone | **Canonical source of truth** — product intent, architecture, honest status, the §16 phased roadmap. Start here. |
| [docs/product/deployment-matrix-model.md](./docs/product/deployment-matrix-model.md) | Engineers | Phase 5 design record — the typed property graph on canonical memory. |
| [docs/product/matrix-extraction-agent.md](./docs/product/matrix-extraction-agent.md) | Engineers | Phase 6.2b design record — the Cartographer agent. |
| [docs/product/synthesis-agents.md](./docs/product/synthesis-agents.md) | Engineers | Phase 7.1 design record — Oracle + Master Strategist. |
| [docs/dev-environment.md](./docs/dev-environment.md) | Engineers | Toolchains, pnpm workflows, dev middleware, the compose stack. |
| [docs/repo-layout.md](./docs/repo-layout.md) | Engineers | Workspace map (stale on a few deferred workspaces — being updated). |
| [infra/compose/seed/README.md](./infra/compose/seed/README.md) | Engineers | The repeatable seed for manual testing. |

---

## License

UNLICENSED — see the [`package.json`](./package.json) `license` field.
