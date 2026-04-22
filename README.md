# DeployAI — Agentic Deployment System of Record

> A Canonical-Memory-backed digital twin for long-cycle government deployments. Built to walk the operator into every meeting prepared — with every claim citation-backed, every override logged, and every retrieval deterministically replayable.

**Status:** Planning complete · Implementation starting from `Epic 1` in [`_bmad-output/implementation-artifacts/sprint-status.yaml`](./_bmad-output/implementation-artifacts/sprint-status.yaml).

---

## What this repo is

This repository is the monorepo home for DeployAI. Today it contains the BMAD-method planning artifacts, agent skills, and the sprint plan. Code will land incrementally, one user-visible increment per epic.

## Repository layout

```
DeployAI/
├── _bmad/                        # BMAD agent & workflow configuration
│   ├── _config/                  # Agent manifest, project config
│   ├── bmm/                      # BMAD method config
│   └── core/                     # Core BMAD config
│
├── _bmad-output/                 # BMAD-generated planning + tracking artifacts
│   ├── planning-artifacts/       # prd.md · architecture.md · ux-design-specification.md · epics.md · product brief(s)
│   ├── implementation-artifacts/ # sprint-status.yaml + future story spec files (1-1-*.md, 1-2-*.md, …)
│   └── brainstorming/            # Brainstorming session notes
│
├── .cursor/                      # Cursor IDE config (rules, skills, commands)
│   ├── skills/                   # BMAD skill definitions (bmad-*, etc.)
│   └── rules/                    # Project-wide AI guidance rules
│
└── docs/                         # Additional reference docs (non-BMAD)
```

Future top-level directories (to land per epic):

```
apps/       web (Next.js 16 / React 19) · edge agent (Tauri 2.x / Rust) · foia-cli (Go)
services/   FastAPI Python services (async SQLAlchemy 2.x, Pydantic v2)
packages/   design-tokens · ui · citation-lib · shared schemas
infra/      Terraform + Terragrunt (AWS: ECS Fargate, RDS pgvector, S3, SQS, EventBridge)
tests/      integration, e2e, compliance replay-parity fixtures
.github/    workflows (CI, SLSA provenance, SBOM, a11y gates)
```

## Planning artifacts (start here)

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

## License

TBD.
