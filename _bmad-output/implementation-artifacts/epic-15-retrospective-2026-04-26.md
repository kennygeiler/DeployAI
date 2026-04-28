# Epic 15 retrospective — Customer pilot prerequisites

**Date:** 2026-04-26 · **Scope:** Stories **15-1** through **15-5** (per [`sprint-status.yaml`](./sprint-status.yaml)). **Operator docs:** [`docs/pilot/README.md`](../../docs/pilot/README.md).

## Outcomes (what shipped in-tree)

- **Hosted strategist session model** — tenant role contract for strategist-facing surfaces.
- **Provisioning repeatability** — pilot tenant bootstrap patterns documented and reflected in CP direction.
- **Durability stance** — strategist queue durability called out (CP vs single-replica trade space).
- **Meeting presence** — pilot scope / Graph cache decision recorded.
- **Observability & support** — pilot observability hooks + support runbook alignment.

## What went well

- **Explicit pilot gates:** Epic 15 translated “demo” vs “pilot” into checklist-style requirements that **`whats-actually-here.md`** §10 could reuse verbatim.
- **Bridge to Epic 16:** Onboarding + integrations UX landed as a coherent follow-on epic.

## Learnings and risks

| Theme | Detail |
| ----- | ------ |
| **Single-replica honesty** | Until queues are CP-backed everywhere, pilot docs must stay loud about **one replica** or **accepted data loss** on deploy. |
| **Auth** | Strategist tenant injection vs real SSO remains the critical path for external pilots. |

## Action items (forward)

| Item | Home |
| ---- | ----- |
| Track queue durability adoption | Epic 12–14 integration stories; CP APIs. |
| Refresh pilot checklist when SSO path changes | `docs/pilot/` + §10 FDE section. |

## Parallel longer arc

Epic **16** executed design-partner onboarding while Epic **11–12** advanced edge + FOIA — prerequisites doc (`Epic 15`) intentionally **decoupled** fleet capture from web strategist pilots.
