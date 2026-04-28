# One-tenant pilot — DB-backed queues + hosted SaaS checklist

**Constraints:** Single design-partner tenant for first external pilot; **strategist queues persisted in Postgres** (via control-plane); **multi-replica-safe** web tier (no in-memory `strategist-queues-store` for pilot surfaces).

**References:** [`whats-actually-here.md`](../../whats-actually-here.md), [`pilot-single-tenant-phases-vs-epics.md`](./pilot-single-tenant-phases-vs-epics.md), Epic **15.3** / **16.4–16.5** in [`epics.md`](../planning-artifacts/epics.md).

### Dependency order (implement first → last)

1. **P1** — Postgres schema + Alembic migrations for strategist queues.
2. **P2** — Control-plane internal REST for list / bulk / patch (tenant-scoped).
3. **P3** — `apps/web` BFF proxies to CP when `DEPLOYAI_STRATEGIST_QUEUES_BACKEND=cp` (+ `DEPLOYAI_CONTROL_PLANE_URL`, `DEPLOYAI_INTERNAL_API_KEY`, tenant header).
4. **P4–P11** — loaders, evidence, meetings, ingestion, SSO, etc. (see per-issue “Depends on” below).

**Queue pilot slice status:** P1–P3 are implemented in-repo (migration `20260527_0015_strategist_operator_queues`, `/internal/v1/strategist/*-queue-items`, BFF routes including solidification).

---

## Issue P1 — Strategist queue tables + migrations (tenant-scoped)

**Goal:** Replace in-process queue state with durable rows keyed by `tenant_id` + stable IDs linkable to canonical nodes.

**Acceptance criteria:**

- [ ] Alembic migrations add tables (names TBD in implementation) for **action queue**, **validation queue**, **solidification queue** items — minimum fields: `id`, `tenant_id`, `strategist_user_id`, `status`, `payload_json` (or normalized columns), `canonical_node_ids[]` / `citation_refs`, `created_at`, `updated_at`, `resolution` / `defer_reason` as applicable.
- [ ] RLS policies: tenant isolation matches existing **`tenant_id`** patterns (`SET LOCAL`, session vars).
- [ ] Indexes for list-by-tenant + status + recency.
- [ ] Rollback tested.

**Depends on:** Existing canonical memory / tenancy model (Epic **1.8–1.9**).

---

## Issue P2 — Control-plane REST API for queue CRUD + transitions

**Goal:** Server-side source of truth for queue lifecycle (claim / in-progress / resolve / defer / promote / demote).

**Acceptance criteria:**

- [ ] Authenticated routes under internal or strategist scope (same authz as overrides): list, create (carryover), patch transition; all scoped by `tenant_id`.
- [ ] Claim semantics: optional optimistic locking or unique constraint to prevent double-claim.
- [ ] Audit events emitted on transitions (reuse patterns from overrides/kill-switch).
- [ ] Integration tests: two concurrent claims → one succeeds or explicit conflict.

**Depends on:** P1.

---

## Issue P3 — `apps/web` BFF routes call CP (remove pilot reliance on `strategist-queues-store`)

**Goal:** `/api/bff/*` queue handlers persist via CP API; **no** in-memory store for pilot-enabled tenants.

**Acceptance criteria:**

- [ ] Feature flag or tenant allowlist: **pilot tenant** uses CP-backed paths; others unchanged OR phased rollout.
- [ ] `/action-queue`, `/validation-queue`, `/solidification-review` load from CP after SSR/client fetch.
- [ ] Carryover from in-meeting alert → creates **durable** action-queue row.
- [ ] Playwright smoke path updated for pilot tenant fixture.

**Depends on:** P2.

---

## Issue P4 — Loader defaults: CP/canonical reads for pilot tenant (digest + phase + evening)

**Goal:** Morning digest / phase tracking / evening synthesis materialized from **tenant graph** + Oracle materializations — **`STRATEGIST_*_SOURCE_URL`** unset for pilot.

**Acceptance criteria:**

- [ ] Identify pilot tenant by config (`DEPLOYAI_PILOT_TENANT_ID` or CP flag).
- [ ] Loaders query CP/canonical-memory projections for digest rows (minimum vertical slice per Epic **16.4**).
- [ ] Document fallback: if CP returns empty, show explicit empty state — not silent fixture mix.

**Depends on:** Data present from ingestion (P9 indirectly).

---

## Issue P5 — Evidence deeplink resolution against canonical graph (pilot tenant)

**Goal:** `/evidence/[nodeId]` resolves for IDs emitted by digest/alerts for **that** tenant.

**Acceptance criteria:**

- [ ] Loader (`Epic 16.5` direction) resolves tenant + authorization before returning evidence payload.
- [ ] 404 when ID not in tenant scope (no cross-tenant leakage).

**Depends on:** P4 baseline.

---

## Issue P6 — Meeting presence + activity: pilot tenant uses Graph-backed path (no demo-only signal)

**Goal:** `GET .../meeting-presence` and strategist activity reflect **real** calendar/meeting state for pilot scope.

**Acceptance criteria:**

- [ ] Documented Graph OAuth scopes + CP connector path for pilot tenant.
- [ ] `loadStrategistActivityForActor` shows coherent ingestion + presence + optional Oracle health for pilot — stubs documented only for non-pilot tenants.
- [ ] `/in-meeting` renders off CP-backed presence within documented SLO (may still defer strict **≤8s p95** to hardening).

**Depends on:** Epic **3** connectors live for pilot tenant; Epic **2** tokens.

---

## Issue P7 — Oracle/Cartographer → digest & in-meeting **for pilot tenant**

**Goal:** Ranked suggestions and alert payloads grounded in retrieval over **that tenant’s** canonical events — not demo fixtures.

**Acceptance criteria:**

- [ ] Batch or synchronous jobs write digest artifacts / alert payloads to CP or read-through cache keyed by tenant.
- [ ] Citation envelopes reference **real** `node_id`s from graph for pilot.
- [ ] Graceful degradation when Oracle unavailable (explicit banner — Epic **6.8**).

**Depends on:** P4, P6, ingestion volume.

---

## Issue P8 — Hosted SSO session path for strategist (no dev header injection)

**Goal:** Pilot users authenticate via Entra/OIDC; **`x-deployai-role`** / **`x-deployai-tenant`** from trusted session/proxy — not middleware injection.

**Acceptance criteria:**

- [ ] Documented IdP + CP mapping for pilot tenant.
- [ ] `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1` passes E2E for strategist routes.
- [ ] Remove or gate dev-only injection for pilot deployment profile.

**Depends on:** Epic **2.2–2.4** operationalization.

---

## Issue P9 — Tenant-shaped evaluation slice (correctness guardrail)

**Goal:** Replay-parity / judge corpus extended with **redacted pilot-shaped** fixtures OR synthetic corpus matching pilot schema — CI gate before expanding pilot users.

**Acceptance criteria:**

- [ ] ≥ N scenarios covering digest + alert citation overlap for tenant schema.
- [ ] Failure blocks merge for pilot branch or tagged CI job.

**Depends on:** P7 partial.

---

## Issue P10 — Observability for pilot tenant

**Goal:** Trace IDs from ingestion through digest generation; dashboards or structured logs for pilot support.

**Acceptance criteria:**

- [ ] `tenant_id` on logs for ingestion jobs, Oracle jobs, API handlers.
- [ ] Runbook: [`docs/pilot/support-runbook.md`](../../docs/pilot/support-runbook.md) updated with “how to debug missing digest row.”

**Depends on:** Infra availability (minimal: structured logs acceptable for V1 pilot).

---

## Issue P11 — Pilot kill criteria + waivers document

**Goal:** Written list of **what is still stub** (e.g. ASR mode, secondary integrations) so stakeholders don’t confuse demo depth with product depth.

**Acceptance criteria:**

- [ ] `docs/pilot/waivers-and-stubs.md` (or section in existing pilot README) lists stubs + owners + ETA/post-pilot.

**Depends on:** None (parallel).

---

## Suggested sequencing

```
P1 → P2 → P3          (queues durable end-to-end)
P8 (parallel early)   (auth blocks realistic UAT)
P4 → P5 → P6 → P7     (truth loop + meeting + Oracle)
P9 → P10 → P11        (guardrails + ops + honesty)
```

---

## Out of scope (this checklist)

- Full Epic **12** compliance program.
- Multi-tenant SaaS-scale FOIA **12.2** completion unless contracted.
- Epic **13** usability study execution (schedule separately).
