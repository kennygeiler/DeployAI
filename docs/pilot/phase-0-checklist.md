# Phase 0 — internal dry-run gate (Epic 16.6)

Run **before** external visitors. Record sign-off (ticket or PR comment) when complete.

**Canonical behavior for JWT, tenant headers, and optional header stripping:** [`session-and-headers.md`](./session-and-headers.md) — exercise the checks below against **your hosted URLs**, not localhost defaults.

## Summary gates

| # | Gate | Evidence |
| --- | --- | --- |
| 1 | Hosted web + CP reachable | Health checks green; TLS valid |
| 2 | SSO / JWT | `DEPLOYAI_WEB_TRUST_JWT` + PEM or trusted edge headers; `DEPLOYAI_STRATEGIST_REQUIRE_TENANT` behavior verified |
| 3 | Integrations | At least one M365 path connectable per [`oauth-from-web.md`](./oauth-from-web.md) |
| 4 | Digest slice | `DEPLOYAI_DIGEST_SOURCE=cp` + CP `DEPLOYAI_PILOT_SURFACE_DATA_PATH` (or documented fallback) |
| 5 | Evidence slice | `DEPLOYAI_EVIDENCE_SOURCE=cp` + tenant isolation spot-check |
| 6 | Queue mode | Documented per [`queue-durability-modes.md`](./queue-durability-modes.md) |
| 7 | Runbook | [`support-runbook.md`](./support-runbook.md) linked from on-call channel; product catalog links it (see **Runbook spot-check** below) |
| 8 | Limitations | [`whats-actually-here.md`](../../whats-actually-here.md) reviewed with design partner |

---

## Hardened `apps/web` — environment bundle (hosted pilot)

Set these **deliberately** in your hosted secret store. Do not rely on dev-only defaults (`NODE_ENV=development` injects a strategist role when headers are unset — **not** present in production; see [`session-and-headers.md`](./session-and-headers.md)).

| Variable | Recommended hosted pilot |
| --- | --- |
| `NODE_ENV` | `production` |
| `DEPLOYAI_WEB_TRUST_JWT` | `1` |
| `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` | RSA **public** PEM (SPKI), same trust material as CP signing keys — optional multiple concatenated blocks |
| `DEPLOYAI_JWT_ISSUER` / `DEPLOYAI_JWT_AUDIENCE` | Match [`services/control-plane`](../../services/control-plane) JWT issuance (defaults: `deployai-control-plane`, `deployai`) |
| `DEPLOYAI_WEB_ACCESS_TOKEN_COOKIE` | Only if overriding default cookie name (`deployai_access_token`) |
| `DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT` | Optional `1` — strip inbound `x-deployai-role` / `x-deployai-tenant` **before** JWT runs (**JWT-only identity path**). Leave unset if the edge injects trusted headers **without** JWT on the web app. |
| `DEPLOYAI_STRATEGIST_REQUIRE_TENANT` | `1` — strategist pages + `/api/bff/*` + `/api/internal/strategist-activity` require tenant after middleware (`tid` from JWT satisfies when JWT trust is on). |
| `DEPLOYAI_CONTROL_PLANE_URL` | HTTPS base URL reachable from the web runtime |
| `DEPLOYAI_INTERNAL_API_KEY` | Matches CP internal API expectation |
| `DEPLOYAI_DISABLE_DEV_STRATEGIST` | N/A in production (dev injection already off); set `1` in staging only when explicitly testing **without** auto role |

---

## Control plane — pilot surface file + web loaders

| Where | Variable | Purpose |
| --- | --- | --- |
| **Control plane host** | `DEPLOYAI_PILOT_SURFACE_DATA_PATH` | JSON file backing pilot-surfaces routes (see [`examples/pilot-surface.example.json`](./examples/pilot-surface.example.json)) |
| **`apps/web`** | `DEPLOYAI_DIGEST_SOURCE=cp` | `/digest` via CP pilot-surfaces |
| **`apps/web`** | `DEPLOYAI_EVIDENCE_SOURCE=cp` | `/evidence/[nodeId]` via CP |
| **`apps/web`** | `DEPLOYAI_PILOT_TENANT_ID` *(optional)* | One-tenant pilot: match JWT `tid` so loaders resolve without global `*_SOURCE=cp` |

Align **`DEPLOYAI_ORACLE_HEALTH_URL`** on web if Oracle HTTP liveness should participate in degraded banners ([`oracle-and-digest-pilot.md`](./oracle-and-digest-pilot.md)).

---

## Hosted verification procedure

Walk gates **in order**. Capture **URLs**, **HTTP status**, or **screenshot references** in the sign-off notes.

### Gate 1 — Reachability & TLS

- **Web:** HTTPS GET to a strategist route (e.g. `/digest`) returns **200** when authenticated as intended for production testing (see Gate 2), or the expected redirect to IdP — **not** certificate warnings.
- **CP:** `GET {DEPLOYAI_CONTROL_PLANE_URL}/healthz` returns **200** with OK body.

### Gate 2 — JWT + tenant (matches [`session-and-headers.md`](./session-and-headers.md))

Confirm **your** deployment’s story: **JWT path (1)** and/or **trusted edge headers (2)**.

**With JWT trust + PEM (`DEPLOYAI_WEB_TRUST_JWT=1`):**

1. **Browser:** After sign-in, strategist shell loads (`/digest`, etc.) without manual header tooling; tenant-bound surfaces reflect JWT claims (`tid`).
2. **Invalid credential:** Request with a bad/expired Bearer or cookie token → **401** (`middleware` rejects invalid JWT material before spoofed headers matter).
3. **`DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`:** With JWT trust on, absence of valid tenant resolution must not yield strategist pages **without** tenant — behavior matches [`middleware.ts`](../../apps/web/middleware.ts) + doc (JWT `tid` satisfies tenant header once applied).

**Optional `DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT=1`:**

- Enable **only** when identity comes from JWT/cookie on this app — **not** when production relies solely on reverse-proxy–injected `x-deployai-*` without JWT verification here.

### Gate 3 — Integrations

Complete at least one path from [`oauth-from-web.md`](./oauth-from-web.md) (connect / status / recover) against hosted CP + web.

### Gate 4 — Digest (CP loader)

- Set **`DEPLOYAI_DIGEST_SOURCE=cp`** on web and **`DEPLOYAI_PILOT_SURFACE_DATA_PATH`** on CP with JSON populated for the pilot tenant.
- Open **`/digest`** — top items match expectations from your pilot surface file or documented deviation.

### Gate 5 — Evidence (tenant isolation)

- From **`/digest`**, open an evidence deeplink **`/evidence/{nodeId}`** that exists for the tenant.
- Spot-check **wrong tenant / unknown node** → CP returns **404**; UI must not show another tenant’s payload (see hosted-environment digest/evidence bullets).

### Gate 6 — Queue durability mode

- Record **Option A** (CP-backed / `DEPLOYAI_STRATEGIST_QUEUES_BACKEND=cp`) vs **Option B** (single replica + in-memory BFF store) per [`queue-durability-modes.md`](./queue-durability-modes.md).
- If multi-replica web without CP-backed queues, note explicit risk — aligns with [`whats-actually-here.md`](../../whats-actually-here.md) §10 queue bullet.

### Gate 7 — Runbook spot-check

- Publish [`support-runbook.md`](./support-runbook.md) in your **on-call / Slack / wiki** channel (paste URL).
- Confirm catalog reference: **[whats-actually-here.md §10 Support](../../whats-actually-here.md)** links this runbook — anyone triaging incidents has one hop to pilot triage steps.

### Gate 8 — Limitations review

- Walk **[whats-actually-here.md](../../whats-actually-here.md)** with the design partner (fixtures, queues, meeting presence scope) — no surprise “CI vs reality” gaps during their session.

---

## Sign-off template

- **Date:**
- **Environment:** (URLs redacted if needed)
- **Owner:**
- **JWT mode:** JWT trust + PEM / edge headers only / hybrid — notes:
- **`DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT`:** on | off — rationale:
- **Queues mode:** Option A | Option B — notes:
- **Evidence:** digest + evidence CP verification pointer (ticket/screenshots):
- **Runbook:** link posted at:
- **Notes / deviations:**
