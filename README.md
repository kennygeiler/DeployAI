# DeployAI — Agentic Deployment System of Record

> A Canonical-Memory-backed digital twin for long-cycle government deployments. Built to walk the operator into every meeting prepared — with every claim citation-backed, every override logged, and every retrieval deterministically replayable.

**Status:** **Epics 1–3** are **done** (foundations, identity/SSO, ingestion). **Epic 4** is **in progress** (Story **4-1** LangGraph + Postgres checkpointer stub in [`services/cartographer`](./services/cartographer/) is **done**; remaining 4-2+ stories in backlog). Epics 5+ are not started. The single source of truth for story states is [`_bmad-output/implementation-artifacts/sprint-status.yaml`](./_bmad-output/implementation-artifacts/sprint-status.yaml).

---

## What this repo is

This is the **DeployAI monorepo**: a **polyglot** codebase (TypeScript/Next.js, Python/FastAPI, Go, Rust/Tauri) with **enforced CI** (smoke, a11y, schema, fuzz, SBOM, CVE, integration tests) on every PR to `main`, plus **BMAD** planning under `_bmad-output/` and agent skills under `.cursor/skills/`. It is not a “planning only” tree—`apps/`, `services/`, `packages/`, `tests/`, and `infra/compose` contain shipping or story-delivered code paths.

## Where things live (quick map)

| Area | Notes |
|------|--------|
| `apps/web` | Next.js app (admin shell, a11y-gated) |
| `apps/edge-agent` | Tauri desktop agent |
| `apps/foia-cli` | Go CLI |
| `services/control-plane` | FastAPI: tenancy, M365/Slack/Gmail-style integrations, upload flows, **pytest** + Docker integration |
| `services/ingest` | Ingestion worker stack (Epic 3) |
| `services/cartographer` | **Epic 4-1** LangGraph stub, citation envelope path, `uv` + pytest in **turbo** |
| `packages/` | design-tokens, contracts, `llm-provider`, authz, etc. |
| `tests/` | Continuity, tenant-isolation fuzz, and other cross-workspace harnesses |
| `infra/compose` | Local docker-compose dev stack |
| `.github/workflows/` | CI, a11y, compose-smoke, schema, fuzz (see [workflows README](./.github/workflows/README.md)) |

## Repository layout (directory tree)

See [`docs/repo-layout.md`](./docs/repo-layout.md) for the full convention (adding workspaces, `pnpm` + `uv`, Turbo).

At a glance:

```
DeployAI/
├── apps/          # web (Next.js) · edge-agent (Tauri) · foia-cli (Go)
├── services/      # control-plane · ingest · cartographer · `services/_shared/*`
├── packages/      # design-tokens, contracts, llm-provider, authz, …
├── infra/         # compose dev env · Terraform/Terragrunt
├── tests/         # continuity-of-reference, tenant-isolation fuzz, …
├── docs/          # dev env, a11y gates, security, repo-layout, …
├── .github/       # workflows (CI, a11y, dependabot) · CODEOWNERS
├── _bmad/         # BMAD agent & workflow configuration
└── _bmad-output/  # PRD, epics, sprint-status, retrospectives, stories
```

## Planning & tracking (start here for “what’s next”)

| Document | Purpose |
|---|---|
| [`_bmad-output/planning-artifacts/prd.md`](./_bmad-output/planning-artifacts/prd.md) | 79 FRs · 78 NFRs · 12 design-philosophy commitments |
| [`_bmad-output/planning-artifacts/architecture.md`](./_bmad-output/planning-artifacts/architecture.md) | Tech stack, deployment, compliance, 28 ARs |
| [`_bmad-output/planning-artifacts/ux-design-specification.md`](./_bmad-output/planning-artifacts/ux-design-specification.md) | Visual system, custom components, 43 UX-DRs |
| [`_bmad-output/planning-artifacts/epics.md`](./_bmad-output/planning-artifacts/epics.md) | 14 epics · 123 stories · full FR coverage map |
| [`_bmad-output/implementation-artifacts/sprint-status.yaml`](./_bmad-output/implementation-artifacts/sprint-status.yaml) | Machine-readable sprint tracking |

## Core product principles (non-negotiable)

1. **Mandatory citations** — every agent output carries a signed citation envelope (RFC 3161).
2. **Deterministic replay-parity** — LangGraph checkpoints enable bit-identical replay for compliance.
3. **Three-layer tenant isolation** — app-level `TenantScopedSession` + Postgres RLS + per-tenant KMS envelope encryption.
4. **Compliance-native** — FIPS 140-2, NIST AI RMF mapping, SLSA L2, SBOM (SPDX/CycloneDX), US-only data residency.
5. **Earned-trust UX** — WCAG 2.1 AA + Section 508 enforced by CI-blocking a11y tests from Epic 1 onward.

## The defining user journey

> **07:00** · Morning Digest surfaces "Permit #2231 blocked by DEP sign-off; last action 9 days ago."
> **10:03** · In-Meeting Alert fires during the DOT standup with the *identical citation chip* — same evidence, same RFC-3161 timestamp, same override history — so the operator can act immediately without context-switching.

Every story in `epics.md` serves this moment.

## Working with BMAD in this repo

This project uses the [BMAD Method](./.cursor/skills/) — specialized AI agents for planning, execution, and review. Common entry points:

- `bmad-help` — "what should I do next?"
- `bmad-sprint-status` — human-readable sprint summary
- `bmad-create-story` — author the next story spec from `sprint-status.yaml`
- `bmad-dev-story` — execute a fully-specced story
- `bmad-code-review` — adversarial review of a change
- `bmad-party-mode` — convene multiple agents for a group discussion

## Development & testing

- **Local setup:** [docs/dev-environment.md](./docs/dev-environment.md) — **Node 24.x** (see [`.nvmrc`](./.nvmrc); root `engines` rejects e.g. Node 25 with `ERR_PNPM_UNSUPPORTED_ENGINE`), pnpm, **uv** (Python), Go, Rust as needed per workspace.
- **Smoke / CI loop:** from the repo root, `pnpm install` and `pnpm turbo run lint typecheck test build` (see `turbo.json` for the full graph); Python services also use `uv sync` / `uv run …` in their directories.

## Testing (control plane + cartographer + CI)

`services/control-plane` is covered by a default **unit** `pytest` run and a Docker-backed **integration** suite; see [services/control-plane/README.md — Tests](./services/control-plane/README.md#tests). The **Control plane (integration)** job in [`.github/workflows/ci.yml`](./.github/workflows/ci.yml) runs the full `tests/integration/` tree on every PR to `main`. **Cartographer (Epic 4-1):** the **smoke** job’s `pnpm turbo run test` includes workspace [**@deployai/cartographer**](./services/cartographer/) (`uv run pytest` under the hood) so the LangGraph stub and citation-envelope path stay exercised on every PR.

**`main` ruleset (GitHub):** A repository **ruleset** is defined in [`scripts/github/main-ruleset.json`](./scripts/github/main-ruleset.json) (applied 2026-04-24) and enforces the 14 required checks in [`.github/workflows/README.md`](./.github/workflows/README.md#required-checks-on-main). Re-apply or edit via [`scripts/github/README.md`](./scripts/github/README.md#classic-branch-protection-vs-repository-ruleset-no-double-enforcement). If **classic branch protection** and the **ruleset** both target `main`, remove the duplicate so only one enforces; details are in that README.

**Retrospectives** for closed epics: [`epic-2-retrospective-2026-04-23.md`](./_bmad-output/implementation-artifacts/epic-2-retrospective-2026-04-23.md) · [`epic-3-retrospective-2026-04-23.md`](./_bmad-output/implementation-artifacts/epic-3-retrospective-2026-04-23.md). **Backlog follow-ups (Epic 3):** [deferred-work.md — Epic 3 section](./_bmad-output/implementation-artifacts/deferred-work.md#epic-3-backlog-follow-ups-2026-04-23).

## License

TBD.
