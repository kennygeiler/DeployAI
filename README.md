# DeployAI

[![Node](https://img.shields.io/badge/node-24.x-339933?logo=nodedotjs)](./.nvmrc)
[![pnpm](https://img.shields.io/badge/pnpm-workspace-f69220?logo=pnpm)](./pnpm-workspace.yaml)
[![Turbo](https://img.shields.io/badge/build-turbo-000000?logo=turborepo)](./turbo.json)
[![License](https://img.shields.io/badge/license-UNLICENSED-lightgrey.svg)](./README.md#license)

**Agentic deployment system of record** — a canonical-memory–oriented workspace for long-cycle deployments. This repository is aimed at **teams that host and harden strategist-facing web** (digest, meeting-time surfaces, queues) against a **control plane** and optional data feeds — not at claiming every surface is already backed by production-shaped tenant data.

---

## Overview

DeployAI combines a **Next.js strategist application** (`apps/web`), **FastAPI control plane** and related services, **shared UI and contracts**, and **heavy CI gates** (lint, typecheck, tests, accessibility, compose smoke). Much of the engineering is real: schemas, tenant isolation tests, ingestion direction, agent eval contracts, and production-shaped routes.

For **what is fixture vs live today**, and how far “demo” is from “pilot” and “production,” read the living catalog in [whats-actually-here.md](./whats-actually-here.md) (especially **§1**, **§2**, **§8**, and **§10**). It is the honest baseline for evaluations and hosted pilots.

---

## What’s included

- **Strategist web surfaces** — digest, phase tracking, evening synthesis, in-meeting alert, action / validation / solidification queues, evidence deep links, overrides and personal audit routes; data can come from **fixtures**, **optional HTTP JSON URLs**, **control-plane pilot loaders**, or **BFF helpers** depending on configuration.
- **Control plane & BFF boundary** — meeting presence, ingestion and health signals for activity banners, internal APIs for integrations and pilot surfaces; **queue state** in typical dev/demo paths uses an **in-process BFF store** (see truth doc for multi-replica caveats).
- **Polyglot monorepo** — Node/pnpm workspaces, Python (`uv`) for control plane and agents, Go FOIA CLI, Rust/Tauri edge agent; Dockerfiles and [local compose stack](./docs/dev-environment.md#7-local-stack-via-docker-compose-story-17) for a reference environment.
- **Quality gates** — Turbo pipelines, Playwright E2E where scoped, Storybook and accessibility runners documented under [docs/dev-environment.md](./docs/dev-environment.md).

Capabilities above describe **what you can run and test**, not a completion checklist — use [whats-actually-here.md](./whats-actually-here.md) for stage (“demo” vs “pilot”) language.

---

## Quick start

**Prerequisites:** **Node 24.x** and **pnpm 10.x** (see root `package.json` `engines` and [.nvmrc](./.nvmrc)). `pnpm` refuses unsupported Node majors.

```bash
git clone https://github.com/kennygeiler/DeployAI.git
cd DeployAI
pnpm install --frozen-lockfile
pnpm --filter @deployai/web dev
```

The web app serves on **http://localhost:3000** by default.

**Development-only strategist access:** In `NODE_ENV=development`, [`apps/web/middleware.ts`](./apps/web/middleware.ts) can inject `x-deployai-role: deployment_strategist` when headers are missing, and route handlers mirror that default so strategist APIs do not 401 in local dev. To turn that off: `DEPLOYAI_DISABLE_DEV_STRATEGIST=1 pnpm --filter @deployai/web dev`. Full behavior, poll intervals, and pilot switches are documented in [docs/dev-environment.md](./docs/dev-environment.md) (see **Strategist UI (`next dev`)**).

**Optional full local stack (Postgres, Redis, MinIO, control plane, seeded web):** from the repo root, `make dev` and `make dev-verify` as described in [docs/dev-environment.md §7 — Local stack via docker-compose](./docs/dev-environment.md#7-local-stack-via-docker-compose-story-17).

**CI-style verification** on a clean machine: `pnpm turbo run lint typecheck test build` (see [docs/dev-environment.md](./docs/dev-environment.md) for toolchain breadth and smoke expectations).

---

## Configuration & deployment

| Topic | Where to start |
| --- | --- |
| **Env template & strategist variables** | [.env.example](./.env.example) — control plane URLs, internal keys, OIDC placeholders, `STRATEGIST_*` and pilot-related web vars (comments in file). |
| **Hosted pilot operator pack** | [docs/pilot/README.md](./docs/pilot/README.md) — session, digest/evidence loaders, queues, runbooks. |
| **JWT, tenant, and header boundaries** | [docs/pilot/session-and-headers.md](./docs/pilot/session-and-headers.md) — `DEPLOYAI_WEB_TRUST_JWT`, PEM, issuer/audience, `DEPLOYAI_STRATEGIST_REQUIRE_TENANT`, optional `DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT`. |
| **Hardening checklist (TLS, CP coupling, loaders)** | [docs/pilot/hosted-environment.md](./docs/pilot/hosted-environment.md). |
| **Pre–external-visitor verification** | [docs/pilot/phase-0-checklist.md](./docs/pilot/phase-0-checklist.md) — reachability, JWT/tenant, integrations, digest/evidence CP mode, queue durability mode, runbook, limitations review. |
| **Demo vs pilot distance** | [whats-actually-here.md §10](./whats-actually-here.md#10-fde-field-evaluation-pilot) — minimum credible hosted build and queue/replica warnings. |

Production and pilot deployments should use **secrets from a vault**, not committed `.env` files. Align web and control plane URLs, keys, and JWT trust material per the pilot docs above.

---

## Documentation index

| Document | Audience | Purpose |
| --- | --- | --- |
| [whats-actually-here.md](./whats-actually-here.md) | Strategists, hosts, PM | Fixture vs live surfaces, demo checklist, pilot distance, FDE checklist. |
| [docs/dev-environment.md](./docs/dev-environment.md) | Engineers | Toolchains, `pnpm` workflows, strategist dev middleware, compose stack, smoke commands. |
| [docs/pilot/README.md](./docs/pilot/README.md) | Hosted pilot operators | Index of pilot runbooks and env bundles. |
| [_bmad-output/planning-artifacts/epics.md](./_bmad-output/planning-artifacts/epics.md) | **Internal planning only** | Epic and story grid; not a public delivery promise — pair with **whats-actually-here** for reality. |

Supporting references: [docs/human-ops-runbook.md](./docs/human-ops-runbook.md) (secrets, CI, release operations), [.github/workflows/README.md](./.github/workflows/README.md) (automation overview).

---

## Repository layout

Brief map of top-level areas:

| Path | Role |
| --- | --- |
| `apps/web` | Next.js strategist and admin routes, BFF route handlers, tests. |
| `apps/edge-agent` | Tauri desktop agent (Rust + Vite frontend). |
| `apps/foia-cli` | Go CLI for FOIA-oriented workflows. |
| `services/control-plane` | FastAPI control plane and internal APIs. |
| `services/` (other) | Ingestion, agents, shared service utilities. |
| `packages/` | Design tokens, contracts, `shared-ui`, authz, adapters. |
| `infra/compose` | Docker Compose reference stack and seeds. |
| `docs/` | Engineering and pilot documentation. |
| `_bmad-output/` | Internal planning artifacts (PRD, architecture, sprint status). |

More detail: [docs/repo-layout.md](./docs/repo-layout.md).

---

## License

UNLICENSED — see [`package.json`](./package.json) `license` field.
