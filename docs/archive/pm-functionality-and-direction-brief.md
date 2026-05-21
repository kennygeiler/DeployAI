> **ARCHIVED — superseded.** Its content was merged into the canonical doc.
> Current source of truth: [`docs/product/deployai-source-of-truth-spec.md`](../product/deployai-source-of-truth-spec.md).
> Delivery status: [`_bmad-output/implementation-artifacts/sprint-status.yaml`](../../_bmad-output/implementation-artifacts/sprint-status.yaml).
> Do not use this file for current development — its claims were not re-verified against code.

# PM brief — DeployAI functionality & direction

**Companion to:** [`deployai-source-of-truth-spec.md`](./deployai-source-of-truth-spec.md) (architecture + flags). **Not** a substitute for [`_bmad-output/implementation-artifacts/sprint-status.yaml`](../../_bmad-output/implementation-artifacts/sprint-status.yaml).

---

## What users can do today

- **Run the full strategist shell in a browser:** morning digest, phase tracking, evening synthesis, in-meeting alert surface, action / validation / solidification queues, evidence deep links, overrides composer + history, personal audit, integrations settings, command palette and navigation chrome — implemented under **`apps/web`** (see source-of-truth **§ Strategist UX surfaces**).
- **Operate in three “truth” bands** (often mixed in one deploy):
  - **Demo / dev:** built-in fixtures, optional `STRATEGIST_*` JSON URLs, **queues require CP** (`DEPLOYAI_CONTROL_PLANE_URL` + `DEPLOYAI_INTERNAL_API_KEY`), URL/query flags for meeting and degraded banners (production-gated for meeting URLs).
  - **Hosted pilot:** JWT + tenant headers (or trusted edge), control plane URL + internal key, optional **`DEPLOYAI_PILOT_TENANT_ID`** / **`DEPLOYAI_*_SOURCE=cp`** so digest/evidence/phase/evening read from **CP pilot surfaces**; queues **always** durable in **CP Postgres** when DB migrated.
  - **Operator / admin adjuncts:** internal schema proposals, ingestion run visibility, adjudication shells — scoped routes and CP APIs as wired today.
- **Caveats to state plainly in pilot comms:**
  - **Meeting “in session”** is **stub tenants**, **URL demo**, or **`detection_source: off`** — not universal live calendar truth.
  - **Pilot digest/evidence rows** on CP come from **operator-supplied JSON** (**`DEPLOYAI_PILOT_SURFACE_DATA_PATH`**), not automatic canonical-memory projection for every account.
  - **Epic 12** (FOIA bundle / compliance program) is **still in motion** at the epic level per sprint grid — do not promise full external auditor shell from strategist UX alone.

---

## What we’re building toward (next 1–2 milestones)

Aligned to **ship-fast pilot** docs (**`docs/pilot/*`**, **`docs/production/product-strategy-ship-fast-decisions.md`**) and **`sprint-status.yaml`**:

1. **Close Epic 12 compliance/export debt** starting with **story 12-2** (review) and sequencing backlog **12-3+** as capacity allows — external auditor, break-glass operability, and long-lead compliance artifacts remain **backlog** at epic level.
2. **Harden hosted pilot defaults:** correlation **observability** parity with written rollout (**`correlation-ids-rollout.md`** vs CP implementation), and **meeting presence** progression from stub/`off` toward **Graph/cache**-backed signal (**Epic 15.4 / 9.1** themes).
3. **Data plane depth (post-pilot):** canonical-memory → strategist **projections** (today: **types only** in **`strategist-canonical-projections.ts`**) so digest/evidence are not limited to **file-backed** pilot payloads.

---

## Decisions already embodied in code

- **JWT path for hosted strategist:** optional **`DEPLOYAI_WEB_TRUST_JWT`** verifies CP access JWT and sets **`x-deployai-tenant`** from claim **`tid`**; invalid token → **401**; optional **header strip** before JWT when **`DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT=1`**.
- **Tenant required on strategist routes** when **`DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`** — **403** without **`x-deployai-tenant`**.
- **Queues:** explicit **memory vs CP** backend; **production fail-closed** when **CP** mode is selected but CP env is incomplete (unless break-glass memory fallback flag).
- **Strategist CP data:** pilot tenant match or **`DEPLOYAI_DIGEST_SOURCE` / `EVIDENCE_SOURCE` / `PHASE_TRACKING_SOURCE` / `EVENING_SYNTHESIS_SOURCE`** toggles **`cp`** — see **`strategist-pilot-tenant.ts`**.
- **External auditor** is **denied** strategist / BFF canonical surfaces in middleware (**403** with explicit copy).
- **Meeting URL demos** suppressed in production unless **`NEXT_PUBLIC_DEPLOYAI_STRATEGIST_MEETING_URL_DEMO=1`**.

---

## Open decisions (ambiguous in code or behind future work)

- **Exact CP logging shape** for correlated internal access (doc promises **log `correlation_id`**; dedicated CP middleware/logger not present in this tree — see source-of-truth **Observability** and **P0**).
- **Calendar vs stub vs cache** for **`meeting-presence`** when to flip **`detection_source`** beyond **`off` / stub list** — contract exists; **Graph** implementation depth is the open work.
- **When to retire file-backed pilot surfaces** in favor of **canonical projections** for design partners — **not** wired; **`DEPLOYAI_STRATEGIST_CANONICAL_PROJECTIONS_STUB`** remains **reserved**.
