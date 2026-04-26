# Epic 8 hardening (implementation) — 2026-04-26

Code changes on `main` (via PR) to close more of Stories **8.4–8.7** and **8.2** (filters) / **8.5** (SessionBanner slot, nav targets):

| Area | Change |
| ---- | ------ |
| **8.4** | `GET` `/evidence/[nodeId]` for digest + action-queue node ids; `getStrategistEvidenceByNodeId`; breadcrumbs; `DigestEvidenceCard` `defaultExpanded`. |
| **8.5** | `SessionBanner` in `AppShell` when `STRATEGIST_DEMO_SESSION_BANNER=1`; placeholder pages for nav (`/validation-queue`, `/solidification-review`, `/overrides`, `/audit/personal`). |
| **8.2** | Assignee filter chips on phase tracking. |
| **Middleware** | Role gate extended to new strategist paths. |
| **8.1** | “What I ranked out” was already in `MorningDigest` — unchanged. |
| **Tests** | Vitest for evidence lookup; Playwright for `/evidence/...` + placeholder 200. |

**Still not done (needs agents/backends):** Oracle-backed digest, NFR2/NFR3 jobs, NFR4 p95 in prod-like CI, real `agent_error` bus, canonical-memory **search** in Cmd+K, full VPAT/axe journeys.

**See also:** [`epic-8-implementation-status.md`](./epic-8-implementation-status.md) (if merged from docs branch) for full gap table.
