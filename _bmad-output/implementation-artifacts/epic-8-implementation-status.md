# Epic 8 — implementation status (vs `epics.md`)

**Date:** 2026-04-28 · **Epic 8 (sprint grid):** stories **8-1–8-7** marked **done** in [`sprint-status.yaml`](./sprint-status.yaml); spec deltas vs `epics.md` remain below. **Epic 8 in PRD:** [epics.md §Epic 8](../planning-artifacts/epics.md#epic-8-morning-digest-phase-tracking--evening-synthesis-surfaces)

This document records what is **in `main` today** against Stories **8.1–8.7**. The original acceptance criteria in `epics.md` are **not** all satisfied; treat shipped work as a **V1 walking skeleton** for strategist surfaces, not a closed epic under the full letter of the spec.

| Story | Spec intent | In tree (summary) | Gaps vs `epics.md` ACs (representative) |
| ----- | ----------- | ------------------- | ---------------------------------------- |
| **8.1** | Morning Digest | `apps/web/src/app/(strategist)/digest/page.tsx` → `/digest`; `MorningDigest` + mock from `lib/epic8`; responsive layout. | No production Oracle (6.3–6.5) feed; no “What I ranked out” from 6.4; no NFR2 job timing; no integration test with seeded tenant + real citations. |
| **8.2** | Phase & Task Tracking | `…/phase-tracking/page.tsx` → `/phase-tracking`; `PhaseTracking.client.tsx` (TanStack Table, filters, `aria-sort` intent). | Full Action Queue detail contract; all filter chips (assignee, date) as specified; NFR5 measured end-to-end. |
| **8.3** | Evening Synthesis | `…/evening/page.tsx` → `/evening`; `EveningSynthesis` + mock. | 19:00 delivery job; Class B / `/solidification-review` link to Epic 9. |
| **8.4** | Expand-inline citation | `DigestEvidenceCard`, `EvidencePanel` usage in epic8 clients; Playwright for command palette (related E2E). | NFR4 ≤ 1.5 s p95 E2E; “navigate to source” to `/evidence/:node_id` with live routing as specified. |
| **8.5** | Nav chrome | `AppShell`, `StrategistNav`, `ChromeTopBar` under `components/chrome/`; `PhaseIndicator`, `FreshnessChip`; landmarks via layout. | 240 / 56 px and collapse behavior to spec; full nav sections (e.g. Validation Queue, override/history) as listed; `SessionBanner` slot; breadcrumbs on nested records only. |
| **8.6** | Cmd+K palette | `StrategistCommandPalette.client.tsx`; surface navigation; E2E. | “Global search (canonical memory)”; full verb/action categories as specified. |
| **8.7** | Degraded agents + ingest | `load-strategist-activity.ts` (CP `ingestion-runs` + optional Oracle health); `StrategistShell` merges demo query flags; `AgentOutageBanner` + top-rail ingest; per-surface FR46 copy; digest “ranked out” + evening patterns hidden when degraded; Playwright on `/digest`, `/evening`, `/phase-tracking` + unmocked `?agentError=1` / `?ingest=1`. | Live Oracle **agent_error** event bus (vs HTTP health only); full “canonical-memory-only” data plane vs mock citations. |

**Conclusion for planning:** Epic 8 is **not** “complete” in the sense of every **Given/When/Then** in `epics.md`. It **is** ready as a **composable base** for hardening (data wiring, performance tests, a11y journey scripts, nav completeness) and for **Epic 9** queue/in-meeting work in parallel where dependencies allow.

**Related:** [Epic 8 retrospective (2026-04-26, updated 2026-04-28)](./epic-8-retrospective-2026-04-26.md) · [Epic 9 retrospective (2026-04-28)](./epic-9-retrospective-2026-04-28.md) · [FDE pilot — `whats-actually-here.md` §10](../../whats-actually-here.md#10-fde-field-evaluation-pilot).
