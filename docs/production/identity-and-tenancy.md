# Production identity and tenancy (`apps/web`)

## Purpose and scope

This document describes **how strategist identity and tenant context must be established in production** for `apps/web`: SSO/session alignment with control-plane JWTs or trusted edge headers, hardening toggles, and how failures surface. It complements pilot/runbook material but focuses on **deployed production** (`NODE_ENV=production`, no dev-only defaults).

For **local development** (automatic strategist role injection, `DEPLOYAI_DISABLE_DEV_STRATEGIST`, Route Handler fallbacks), see [dev-environment.md](../dev-environment.md) and [session-and-headers.md](../pilot/session-and-headers.md).

---

## Hosted pilot defaults (parallel lane I — ship-fast)

Implementation follows **Lane I** in the production roadmap (tasks **I-103**, **I-104**; see sibling `parallel-agent-execution-plan.md` when present in-repo) and aligns with **`PS-I-101`–`PS-I-104`** / **`PS-G-02`** rows in `product-strategy-ship-fast-decisions.md` when bundled for hosted pilot.

Operators may override defaults per env; annotate env bundles when doing so.

- **Primary path (`PS-I-101`, `PS-G-02`): Path A —** `DEPLOYAI_WEB_TRUST_JWT=1`, non-empty **`DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM`** mirroring control-plane issuance, Bearer and/or **`deployai_access_token`** cookie (`DEPLOYAI_WEB_ACCESS_TOKEN_COOKIE`).
- **`PS-I-103` / I-103:** Canonical tenant UUID comes from JWT claim **`tid`** (matches CP tenant rows). Single-tenant pilots align **`DEPLOYAI_PILOT_TENANT_ID`** with that UUID for loaders scoped to pilot data.
- **`PS-I-104` / I-104:** With Path A where browsers reach Next with Bearer/cookie, set **`DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT=1`** (strip forged `x-deployai-*` before JWT). **Unset / `0`** for Path B — proxy-only headers with **no** JWT verification inside Next (`PS-I-104` escalation only if ingress topology violates this assumption).
- **I-103:** Enable **`DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`** for hosted strategist pages and strategist APIs whenever every call must be tenant-scoped.
- **`PS-I-102`:** Issuer/audience pairing is treated as freeze for pilots from committed `.env.example` ↔ CP issuance unless deliberately rotated together (`DEPLOYAI_JWT_ISSUER`, `DEPLOYAI_JWT_AUDIENCE`).

---

## Requirements

### SSO / session and transport

- Production deployments must **not** rely on dev middleware injecting `x-deployai-role`. Strategist access must come from **real authentication**: either **control-plane–verifiable access JWTs** or **headers set by a trusted reverse proxy / IdP integration** after SSO terminates upstream.
- Target end state (first-party login): session cookies owned by the app or gateway; access JWT **claims** (`sub`, `tid`, `roles`) stay **aligned** with `services/control-plane` issuance and verification (same issuer, audience, signing keys).

### JWT path vs edge headers

Choose at least one **production** path:

1. **JWT trust on the web app** — Set `DEPLOYAI_WEB_TRUST_JWT=1` and `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` (RSA public PEM in SPKI form; same trust family as control-plane JWT verify). Align `DEPLOYAI_JWT_ISSUER` and `DEPLOYAI_JWT_AUDIENCE` with issuance (defaults: `deployai-control-plane`, `deployai`). Clients send the access token as `Authorization: Bearer …` and/or in the cookie named `DEPLOYAI_WEB_ACCESS_TOKEN_COOKIE` (default `deployai_access_token`). Middleware verifies RS256 and sets `x-deployai-role` and `x-deployai-tenant` from claims (`roles`, `tid`); **valid JWTs override** spoofed inbound `x-deployai-*` headers.

2. **Edge / reverse proxy only** — The gateway sets `x-deployai-role` and `x-deployai-tenant` from IdP identity. The web app does not need `DEPLOYAI_WEB_TRUST_JWT` if no token is presented to Next; **you must still prevent untrusted clients from forging those headers** (strip or overwrite at the edge).

### `DEPLOYAI_WEB_TRUST_JWT`

- When enabled **with** a non-empty PEM, JWT verification gates requests that supply a Bearer token or the configured access-token cookie.
- **Rotation:** `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` may contain **multiple concatenated PEM blocks**; verification tries each until one validates (overlap period during key rotation).

### Optional header strip (`DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT`)

- When `DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT=1` **and** `DEPLOYAI_WEB_TRUST_JWT=1` **and** PEM is configured, middleware **deletes** inbound `x-deployai-role` and `x-deployai-tenant` **before** JWT handling so only Bearer/cookie-derived identity applies (see `apps/web/src/lib/internal/strategist-header-strip-before-jwt.ts`).
- Hosted Path A pilots default **`=1`** per `PS-I-104`; use when SSO terminates at the app with JWT cookies. **Do not** use if production relies solely on proxy-injected headers (no JWT to the app).

### `DEPLOYAI_STRATEGIST_REQUIRE_TENANT`

- When `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`, strategist **pages** (e.g. `/digest`, queues, `/overrides`, `/audit/*`, …) and strategist **APIs** (`/api/bff/*`, `/api/internal/strategist-activity`) return **403** if `x-deployai-tenant` is missing or blank after middleware (`PS-I-103`; `tid` from a verified token satisfies tenant once middleware has set headers).
- Does **not** apply to `/admin/*` routes.
- Default **on** for hosted pilot bundles coordinated with loaders (Lane **I-103**).

### Actor derivation (server)

- **Middleware** (`apps/web/middleware.ts`) enforces role parsing, authorization (`canAccess`), and optional tenant requirement; it forwards mutated headers on the request.
- **Route Handlers / server code** use `getActorFromHeaders` (`apps/web/src/lib/internal/actor.ts`): reads `x-deployai-role` and `x-deployai-tenant`; if role is still missing and `DEPLOYAI_WEB_TRUST_JWT=1`, verifies Bearer/cookie and derives role and tenant from claims; **production** must not depend on the dev-only fallback in `getActorFromHeaders` (that runs only in `development` when `DEPLOYAI_DISABLE_DEV_STRATEGIST` is unset).
- **Subject id** for CP calls uses `getActorIdFromHeaders`: optional `x-deployai-actor-id`, else JWT `sub` when JWT trust is on; dev fallback UUID only in development.

### Failure modes (HTTP)

| Situation | Typical response |
|-----------|------------------|
| Bearer or access-token cookie **present** but **none** verify (wrong key, expired, bad `iss`/`aud`, missing `sub`/`tid`/roles, non-access token) | **401** — request must not fall through to forged headers alone when JWT gate is armed. |
| No usable role after middleware (`x-deployai-role` missing or not a known V1 role) | **403** |
| Role not allowed for path (e.g. `external_auditor` on strategist surfaces) | **403** |
| `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1` and strategist path but empty/missing tenant | **403** |

Operator triage patterns remain in [support-runbook.md](../pilot/support-runbook.md).

### Hosted pilot env bundle (template)

Align `apps/web` secrets with **one** primary posture; hybrid setups need explicit edge + app contracts.

| Concern | Path A: JWT verified on `apps/web` | Path B: Trusted edge headers only |
| -------- | ----------------------------------- | ----------------------------------- |
| Identity source | `DEPLOYAI_WEB_TRUST_JWT=1`, non-empty `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM`, optional cookie name via `DEPLOYAI_WEB_ACCESS_TOKEN_COOKIE` | Upstream sets `x-deployai-role` / `x-deployai-tenant` (clients cannot reach the app with forged values) |
| Issuer / audience | `DEPLOYAI_JWT_ISSUER` / `DEPLOYAI_JWT_AUDIENCE` match control-plane issuance | N/A unless tokens are also verified on the app |
| Tenant gate | `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1` for hosted strategist surfaces | Same |
| Optional header strip | `DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT=1` **defaults on** for hosted Path A per `PS-I-104`; **never** when identity is purely untrusted-proxy headers without JWT fallback | Leave **unset** if production is proxy-only **without** JWT verification in Next.js |

**Key rotation (Path A):** During issuer overlap, paste **concatenated** SPKI public PEM blocks into `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM`. Verification tries each block until one validates (`apps/web/src/lib/internal/deployai-access-jwt.ts`); unit coverage in `deployai-access-jwt.test.ts`.

**Escalations (true `BLOCKED — need human:` only):**

- Physical vault paths, live PEM private material, SSO client secrets, production `DEPLOYAI_INTERNAL_API_KEY` values (**PS-G-03**).
- Binding contractual tenant UUID mandates that **cannot** be mirrored in CP / JWT yet (**PS-I-103** escalate row).
- Ingress topology where Path A strip would **drop valid** proxy-only identity — document Path B explicitly (**PS-I-104** escalate row).
- Signing keys or issuer/audience **frozen by external contract** unavailable to engineers (**PS-I-102** escalate row).

---

## Non-goals

- **Full IdP / Entra** app registration steps, certificate lifecycle, or refresh-token UX — covered by product/epic documentation and your SSO vendor; this doc only states the **web app contract** (headers + optional JWT env).
- **Control-plane** `POST /test/session-tokens` and `DEPLOYAI_ALLOW_TEST_SESSION_MINT` — **internal/test** only; not a production identity source for browsers.
- **Strategist data realism** (CP loaders, queue durability, digest URLs) — see [whats-actually-here.md](../../whats-actually-here.md), [oracle-and-digest-pilot.md](../pilot/oracle-and-digest-pilot.md), [queue-durability-modes.md](../pilot/queue-durability-modes.md).
- **Admin surfaces** (`/admin/*`) tenant model — different operator assumptions; not expanded here.

---

## Acceptance criteria checklist

Use before calling production “ready” for strategist routes.

- [ ] `NODE_ENV=production`; no dependency on dev strategist injection (`DEPLOYAI_DISABLE_DEV_STRATEGIST` irrelevant in production).
- [ ] Either JWT path (`DEPLOYAI_WEB_TRUST_JWT=1` + PEM + aligned `DEPLOYAI_JWT_ISSUER` / `DEPLOYAI_JWT_AUDIENCE`) **or** trusted edge sets `x-deployai-role` / `x-deployai-tenant` with **untrusted client headers stripped/overwritten** at the edge.
- [ ] If JWT trust is on: invalid/expired token with no valid fallback returns **401**, not silent header forgery.
- [ ] Hosted Path A: `DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT=1` unless ingress is Path B documented above.
- [ ] Hosted pilot: `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1` when every strategist call must be tenant-scoped; verified JWT `tid` populates tenant.
- [ ] Key rotation documented: overlapping public PEMs in `DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM` during issuer key cutover.
- [ ] Tenant UUID in CP matches `tid` / `x-deployai-tenant` / `DEPLOYAI_PILOT_TENANT_ID` for pilots (see provisioning/runbook).

---

## References

- Companion production docs — lane task grid and ship-fast **`PS-*`** decision table (merge with sibling PRs as needed): `docs/production/parallel-agent-execution-plan.md`, `docs/production/product-strategy-ship-fast-decisions.md`.
- [whats-actually-here.md](../../whats-actually-here.md) — §8 stages (Demo / Pilot / Production), §10 FDE pilot minimums (SSO, no dev headers).
- [docs/pilot/session-and-headers.md](../pilot/session-and-headers.md) — Authoritative pilot description of middleware, JWT, strip flag, and `DEPLOYAI_STRATEGIST_REQUIRE_TENANT`.
- [docs/pilot/hosted-environment.md](../pilot/hosted-environment.md) — Hardening checklist (identity boundary, CP coupling, loaders).
- [docs/pilot/tenant-provisioning.md](../pilot/tenant-provisioning.md) — Tenant UUID, test session mint (internal), header contract for CP.
- [docs/pilot/phase-0-checklist.md](../pilot/phase-0-checklist.md) — Hosted verification before external pilot visitors.
- [docs/dev-environment.md](../dev-environment.md) — Local overrides and strategist dev defaults.
