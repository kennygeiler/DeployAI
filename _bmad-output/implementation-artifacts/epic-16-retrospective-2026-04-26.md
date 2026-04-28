# Epic 16 retrospective — Design partner pilot (onboarding, integrations, CP loaders)

**Date:** 2026-04-26 · **Scope:** Stories **16-1** through **16-6** (per [`sprint-status.yaml`](./sprint-status.yaml)).

## Outcomes (what shipped in-tree)

- **Onboarding shell** with tenant context — strategist lands in a coherent shell before deep workflows.
- **Integrations UX** — M365 connect, status/reconnect/disconnect flows from web.
- **Loaders** — digest from CP canonical memory; evidence deeplink tenant resolution.
- **Playbook** — Phase 0 dry run / Phase 1 design-partner playbook captured for repeatable customer conversations.

## What went well

- **Loader truth:** Moving digest/evidence toward **CP-backed** shapes reduced “fixture-only” embarrassment in design-partner sessions when env vars set.
- **Integration UX patterns** reused components from Epic 7 — consistent with trust language from Epic 10.

## Learnings and risks

| Theme | Detail |
| ----- | ------ |
| **Tenant resolution edge cases** | Deeplink + loader paths must stay aligned with citation envelope IDs — regression tests when CP schema shifts. |
| **Partner expectations** | “Pilot” means different things to buyers; playbook language must stay synced with [`whats-actually-here.md`](../../whats-actually-here.md). |

## Action items (forward)

| Item | Home |
| ---- | ----- |
| Harden loader error surfaces | Web BFF + CP client. |
| Expand playbook when Epic 12 auditor shell lands | `docs/pilot/` + planning artifacts. |

## Parallel longer arc

Epic **12** (compliance / FOIA / auditor) and Epic **14** (platform expansion) proceed **without** blocking Epic 16 closure — customer onboarding stays on the **web strategist** track while edge + export evolve on separate branches.
