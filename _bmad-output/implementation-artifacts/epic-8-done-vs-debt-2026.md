# Epic 8 — shipped vs technical debt (2026)

## What is wired end-to-end (walking skeleton)

- **Strategist shell** — left/top rail, `SessionBanner` slot, Cmd+K, freshness, phase indicator.
- **Surfaces** — Morning digest, phase tracking, evening synthesis with mock or remote-backed data where noted below.
- **Evidence** — `/evidence/:nodeId` for digest + action-queue mock ids; breadcrumbs.
- **BFF** — `GET /api/internal/strategist-activity` aggregates control-plane liveness, ingestion, optional Oracle health, and strategist-local date.
- **BFF (search)** — `GET /api/bff/strategist-memory-search?q=` proxies `DEPLOYAI_CANONICAL_MEMORY_SEARCH_URL` when set; otherwise in-process mock search over digest + action-queue rows. **Cmd+K** calls this endpoint (debounced ~320ms) when the query is non-empty; empty query shows a static “recent preview” list.

## Environment (operator reference)

| Variable | Service | Purpose |
| -------- | ------- | ------- |
| `DEPLOYAI_CONTROL_PLANE_URL` | Web → CP | Base URL for `/healthz` and `/internal/v1/…` BFF calls |
| `DEPLOYAI_INTERNAL_API_KEY` | Web → CP | `X-DeployAI-Internal-Key` for internal routes |
| `DEPLOYAI_ORACLE_HEALTH_URL` | Web → agent stack | **Optional** full URL (e.g. `http://oracle:8080/healthz`); when unset, agent health is not checked |
| `STRATEGIST_DIGEST_SOURCE_URL` | Web (SSR) | **Optional** `GET` returning JSON array of `DigestTopItem` for `/digest` |
| `DEPLOYAI_CANONICAL_MEMORY_SEARCH_URL` | Web (BFF) | **Optional** search upstream; `q` is forwarded on the request URL as `q` |
| `STRATEGIST_LOCAL_TZ` / `STRATEGIST_DEMO_TODAY` | Web | See `strategist-local-date.ts` |

## `strategist-activity` JSON (contract)

```jsonc
{
  "agentDegraded": true,           // any critical dependency unhealthy
  "ingestionInProgress": true,     // at least one `running` ingest for this tenant
  "strategistLocalDate": "2026-04-23",
  "controlPlane": "ok" | "unconfigured" | "error",
  "agentServiceHealth": "unconfigured" | "ok" | "error"  // Oracle (or other) when URL set
}
```

- **Control plane path** — `GET {base}/healthz` must return `{ "status": "ok" }` before internal APIs; then `GET /internal/v1/ingestion-runs` with tenant scoping: **if `x-deployai-tenant` is missing, no tenant’s runs are used for the “ingesting” flag (FR47).**
- **Oracle** — When `DEPLOYAI_ORACLE_HEALTH_URL` is set, a non-OK response marks `agentServiceHealth: "error"` and sets `agentDegraded` when the rest of the stack is otherwise healthy.

## NFR (explicit posture)

- **NFR2 / NFR3 (07:00 / 19:00 jobs)** — Not enforced in the web app. Scheduled digest/evening delivery remains a **platform / job-runner** concern; document “not in web V1” until Oracle scheduling API exists.
- **NFR4 (≤ 1.5s expand-inline)** — Playwright enforces a **&lt; 2s** budget in CI as slack; tighten or add perf metrics if product requires 1.5s in production.
- **FR47 (ingestion indicator)** — Top rail reflects **running** ingestion runs **scoped to the actor’s tenant** when `x-deployai-tenant` is present.

## Gaps to close next

1. **Replace remaining mocks** with canonical-memory reads and Oracle-ranked digests when APIs exist.
2. **Cmd+K** — Wired to `GET /api/bff/strategist-memory-search` (debounced). Optional: richer preview cards or streaming for large result sets.
3. **Evening + phase** — Same pattern as `STRATEGIST_DIGEST_SOURCE_URL`: optional remote JSON loaders (not yet all extracted to code paths).

See planning artifact `epics.md` (Epic 8 / 9) for product acceptance criteria.
