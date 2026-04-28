# Epic 9 retrospective — In-meeting alert, action queue, validation queues

**Date:** 2026-04-28 · **Scope:** Stories **9-0** through **9-8** + MVP Track E E2E (per [`sprint-status.yaml`](./sprint-status.yaml)). **Living product truth:** [`whats-actually-here.md`](../../whats-actually-here.md).

## Outcomes (what shipped in-tree)

- **Surfaces:** `/in-meeting` with `InMeetingAlertCard` (shared-ui), ranked-out budget, correction vs dismiss flows; `/action-queue`, `/validation-queue`, `/solidification-review` with TanStack tables and BFF JSON routes.
- **Data path:** `GET/POST` BFF handlers backed by **`strategist-queues-store`** (in-process seed + carryover + lifecycle); `loadStrategistActivityForActor` for meeting + degrade signals; Playwright coverage for palette, meeting alert, NFR1-style timing.
- **UX hardening:** FR37 feedback toasts; Story **9.8** — draggable position + header **Reset** + context-menu “Reset position to default”; position persistence documented as **`localStorage` only** (see `whats-actually-here.md` §7).
- **CI:** `shared-ui` built via Turbo so `@deployai/contracts` precedes `tsc`; Vitest cleanup between RTL tests.

## What went well

- **Reuse of Epic 7–8:** Citation chips, evidence panel patterns, and strategist shell meant Epic 9 was mostly **wiring + contracts**, not new visual language.
- **Single activity snapshot:** One poll shape drives banners, meeting chrome, and degrade UX — fewer divergent mocks.
- **Explicit BFF boundary:** Queue mutations stay behind `/api/...` routes; swapping the store for CP later is localized.

## Learnings and risks (no blame)

| Theme | Detail |
| ----- | ------ |
| **Process vs in-memory store** | The BFF store is **correct for demo and single-node dev**; it is **not** multi-instance-safe. Rolling deploys or >1 replica **split or lose** queue state unless you add sticky sessions or external persistence. File header in `strategist-queues-store.ts` now states this for operators. |
| **Spec vs “sprint done”** | Stories can be **done** in the tracker while **pilot** requirements (durable queues, server-side alert layout, real calendar-driven meeting) remain **Epic 10+ / integration** work — keep `whats-actually-here.md` as the honest catalog. |
| **Playwright + types** | Per-test timeout must use `test.setTimeout` when the middle `TestDetails` object does not accept `timeout` under the pinned `@playwright/test` version — caught in CI smoke. |
| **9.8 cross-device** | Operators expect layout to follow them across machines; **localStorage** cannot deliver that — product messaging and a future **CP/user-prefs** story should close the gap. |

## Action items (forward)

| Item | Owner / home |
| ---- | ------------- |
| **CP- or DB-backed queues** for any multi-replica or FDE deployment | Epic 10+ / integration stories; replace `strategist-queues-store` incrementally. |
| **Server or synced prefs** for alert card position (optional) | Small story: CP PATCH + hydrate on `StrategistShell`. |
| **Runbook** for “single replica or demo only” until queues are durable | [`whats-actually-here.md` §10](../../whats-actually-here.md#10-fde-field-evaluation-pilot) (this pass). |
| **Epic 10 kickoff** | Overrides + audit trail — `OverrideComposer` already stubbed in shared-ui. |

## Readiness handoff

- **Epic 10** can start with **10-1 / 10-2** while queue durability is parallel-tracked for pilot.
- **FDE field test** today is credible for **UX + workflow** on **one** stable web instance with dev/strategist auth resolved — not for **fleet-scale** or **survivable** queue state without further build-out.

## Team sentiment (brief)

- **Win:** End-to-end **golden path** (digest → evidence → in-meeting → queues) is demonstrable with fixtures.
- **Tension:** Saying “done” without saying **where data lives** misleads field testers — documentation and store header mitigate that.
