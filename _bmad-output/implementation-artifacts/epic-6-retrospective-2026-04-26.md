# Epic 6 retrospective — Cartographer, Oracle & Master Strategist

**Date:** 2026-04-26 · **Scope:** Stories **6-1** through **6-8** (per [`sprint-status.yaml`](./sprint-status.yaml)).

## Outcomes (what shipped in-tree)

- **Runtime contracts:** Cartographer triage + entity/relationship extraction paths; Oracle retrieval posture (phase-gated, three-item budget, suggestions-only); Master Strategist arbitration + phase-transition proposals; graceful degradation contract.
- **Integration surface:** Wiring toward strategist-facing flows without claiming full production inference loops in the browser.

## What went well

- **Separation of concerns:** Cartographer vs Oracle vs Strategist roles stayed distinct in code and docs — easier to test and to swap providers later.
- **Budget + posture:** Hard budgets and “suggestions only” reduced foot-guns in demo narratives.

## Learnings and risks

| Theme | Detail |
| ----- | ------ |
| **Lab vs product** | Much of Epic 6 is **contract + harness** richness; full browser-loop intelligence remains bounded by Epic 4 harness + CP/agent deployment — align demos with [`whats-actually-here.md`](../../whats-actually-here.md). |
| **Naming drift** | “Oracle” / “Strategist” overloaded in casual speech — API and module names stayed the source of truth. |

## Action items (forward)

| Item | Owner / home |
| ---- | ------------- |
| Keep degradation contracts tested when CP URLs change | Agent runtime + integration tests. |
| Align roadmap language with deployable slices | Planning artifacts + pilot docs. |

## Parallel longer arc

Strategist **UX epics (7–10)** consumed patterns from Epic 6; **Epic 14** tracks successor/strategist inheritance without blocking Epic 12 compliance work.
