# Epic 1 retrospective — Foundations, canonical memory & citation envelope

**Date:** 2026-04-26 · **Scope:** Stories **1-1** through **1-17** (per [`sprint-status.yaml`](./sprint-status.yaml)). **Living product truth:** [`whats-actually-here.md`](../../whats-actually-here.md).

## Outcomes (what shipped in-tree)

- **Monorepo:** pnpm + Turborepo with reproducible `pnpm install --frozen-lockfile` and CI smoke gates.
- **Supply chain:** SBOM, CVE scanning, dependency-review posture; baseline release scaffold deferred intentionally.
- **Apps:** `apps/web` (Next + Tailwind v4 + Storybook + a11y CI), `apps/edge-agent` Tauri spike path, `apps/foia-cli` Go binary, `services/control-plane` FastAPI + Alembic stub.
- **Contracts:** Design tokens package, citation envelope v0.1, tenant isolation fuzz CI, RFC3161 interface plumbing, canonical-memory schema direction.

## What went well

- **Rules of the road early:** CI + format + typecheck culture made later epics mergeable without thrash.
- **Isolation + citation tests:** Paying down “paper architecture” with executable contracts (fuzz + envelope tests) reduced Epic 2–4 integration surprises.
- **Deferred work logged explicitly:** ESLint/next ecosystem pin and other tradeoffs captured rather than hidden.

## Learnings and risks

| Theme | Detail |
| ----- | ------ |
| **Scope breadth** | “Foundations” spanned web, edge, CP, CLI — coordination cost is real; story boundaries helped. |
| **Documentation drift** | Without `whats-actually-here.md`-style honesty, stakeholders confuse **CI green** with **product complete** — later epics adopted that pattern. |

## Action items (forward — mostly absorbed by later epics)

| Item | Home |
| ---- | ---- |
| Keep CI smoke as merge gate | Root workflows + Turbo tasks. |
| Maintain honest catalog | [`whats-actually-here.md`](../../whats-actually-here.md). |

## Parallel longer arc

Epic 1 enables **every** downstream epic; **Epic 14** (post-V1 scaffolding) inherits the same gates without redoing foundations.
