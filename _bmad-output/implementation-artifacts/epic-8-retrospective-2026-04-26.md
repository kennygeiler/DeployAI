# Epic 8 retrospective — Strategist walking skeleton

**Date:** 2026-04-26 (original) · **Updated:** 2026-04-28 · **Scope:** Stories **8-1–8-7** per sprint grid. **PRD fidelity:** not every `epics.md` AC is satisfied — see [`epic-8-implementation-status.md`](./epic-8-implementation-status.md) for the gap table (“V1 walking skeleton” vs full spec).

## Outcomes

- **Surfaces:** `/digest`, `/phase-tracking`, `/evening` with `@deployai/shared-ui` compositions and mock/adaptor-friendly data.
- **Chrome + Cmd+K:** `AppShell`, left nav, `ChromeTopBar` with `PhaseIndicator`, `FreshnessChip`, command palette, ingestion indicator when runs are `running`.
- **Control-plane activity:** BFF-style loading of ingestion runs + `agentDegraded` signal for `AgentOutageBanner` (degrade path when CP check fails).
- **Tests:** E2E around strategist command palette; unit tests for activity loader; middleware/flags for strategist shell.

## What worked

- **Composition over invention:** Epic 7 primitives + tokens kept UI work mostly wiring and copy.
- **CP-backed ingest signal:** A single `GET /internal/v1/ingestion-runs` read gives FR47-style visibility without a new microservice.
- **Same a11y stack as the rest of `apps/web`:** No separate pattern for Story 8; axe/jsx-a11y apply uniformly.

## Learnings and risks

- **Two meanings of “done”:** **Sprint grid:** all 8-x stories **done** — composable shell shipped. **PRD letter:** Oracle schedules, NFR2/NFR4, global palette search, SessionBanner slot, etc. — **hardening** / follow-on. Use `epic-8-implementation-status.md` + `whats-actually-here.md` when talking to FDEs or buyers.
- **Spec vs velocity:** The written epic assumes Oracle-scheduled digests, NFR2/NFR4 measurement, and top-5 SR journeys — a **hardening** track, not a single PR.
- **SessionBanner + breadcrumbs:** Still open for break-glass / nested evidence UX (ties Epic 2 + 12).

## Forward

| Track | Note |
| ----- | ---- |
| **Hardening** | Oracle-backed cards, ranked-out footer, NFR4 E2E, integration tests, SessionBanner slot, global search in palette. |
| **Epic 9** | In-meeting alert, action queues, validation queues — can start in parallel with clear dependency on shared chrome + `CitationChip`. |

## Sentiment (brief)

The skeleton delivers **Journey 1** *demonstrability*; production-grade **FR34/FR35/FR39** need agent and schedule integration beyond UI-only mocks.

## Retrospective closure (BMAD — 2026-04-28)

- **Sprint status:** `epic-8-retrospective` marked **done**; this doc remains the **honest** record that **PRD AC ≠ sprint checkbox** for every line in `epics.md`.
- **Neighbor:** [Epic 9 retrospective — 2026-04-28](./epic-9-retrospective-2026-04-28.md) (queues, in-meeting, BFF limits).
