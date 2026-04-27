# Epic 8 retrospective — Strategist walking skeleton (partial epic)

**Date:** 2026-04-26 · **Scope:** Stories 8.1–8.7 **as implemented on `main`** (not full `epics.md` AC compliance). See [`epic-8-implementation-status.md`](./epic-8-implementation-status.md).

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

- **Spec vs velocity:** The written epic assumes Oracle-scheduled digests, NFR2/NFR4 measurement, and top-5 SR journeys — a **hardening** track, not a single PR.
- **“Epic 8 done” must be defined:** Use this doc + `epic-8-implementation-status.md` to avoid calling the epic closed before agreed gates (e.g. Oracle wire-up + perf E2E) are met.
- **SessionBanner + breadcrumbs:** Still open for break-glass / nested evidence UX (ties Epic 2 + 12).

## Forward

| Track | Note |
| ----- | ---- |
| **Hardening** | Oracle-backed cards, ranked-out footer, NFR4 E2E, integration tests, SessionBanner slot, global search in palette. |
| **Epic 9** | In-meeting alert, action queues, validation queues — can start in parallel with clear dependency on shared chrome + `CitationChip`. |

## Sentiment (brief)

The skeleton delivers **Journey 1** *demonstrability*; production-grade **FR34/FR35/FR39** need agent and schedule integration beyond UI-only mocks.
