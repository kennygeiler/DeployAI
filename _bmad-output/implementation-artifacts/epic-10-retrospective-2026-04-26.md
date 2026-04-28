# Epic 10 retrospective — Override, trust repair & personal audit

**Date:** 2026-04-26 · **Scope:** Stories **10-1** through **10-7** (per [`sprint-status.yaml`](./sprint-status.yaml)). **Living product truth:** [`whats-actually-here.md`](../../whats-actually-here.md).

## Outcomes (what shipped in-tree)

- **Canonical override events** with composer submission, sub-citation in reasoning trails, trust cues, private-scope annotations.
- **Surfaces:** `/overrides` (history + composer) and **`/audit/personal`** backed by **durable** CP APIs where specified — distinction vs in-memory queues called out in operator docs.
- **Crypto plumbing** for private annotations aligned with citation envelope direction.

## What went well

- **Durable vs demo clarity:** Where Epic 9 queues stayed BFF-in-memory, Epic 10 pushed **CP-backed** overrides/audit — honest staging for pilot trust stories.
- **Reuse:** Evidence and citation primitives from Epic 7 carried straight into override UX.

## Learnings and risks

| Theme | Detail |
| ----- | ------ |
| **Pilot wording** | “Personal audit” is credible only when CP tenant boundaries match SSO/session story — Epic 2 + §10 FDE checklist stay coupled. |
| **Supersession complexity** | Citation supersession touches oracle + envelope — regression tests and docs must move together. |

## Action items (forward)

| Item | Home |
| ---- | ----- |
| Continue CP-backed regression tests on overrides | `services/control-plane` + web BFF routes. |
| Operator honesty | [`whats-actually-here.md`](../../whats-actually-here.md) §8 pilot table. |

## Parallel longer arc

Epic **12** (FOIA/compliance) and Epic **14** (platform expansion) proceed in parallel; Epic 10 does not block FOIA CLI or edge agent tracks.
