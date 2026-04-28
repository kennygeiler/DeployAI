# Session and headers (Strategist pilot)

## Today (`apps/web`)

- **Development:** [`middleware.ts`](../../apps/web/middleware.ts) can inject `x-deployai-role: deployment_strategist` when **`NODE_ENV=development`**, **`DEPLOYAI_DISABLE_DEV_STRATEGIST` is not `1`**, and the role header is still unset after optional JWT handling (below). [`getActorFromHeaders`](../../apps/web/src/lib/internal/actor.ts) mirrors that for Route Handlers when the role is still missing.
- **Hosted pilot / production (`next start`):** There is **no** dev role injection. Use either:
  1. **Control-plane access JWT (Story 15.1)** — set **`DEPLOYAI_WEB_TRUST_JWT=1`**, **`DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM`** (RSA public PEM, same trust as [`services/control-plane` JWT verify](../../services/control-plane/src/control_plane/auth/jwt_tokens.py); optional multiple blocks concatenated for rotation), and align **`DEPLOYAI_JWT_ISSUER`** / **`DEPLOYAI_JWT_AUDIENCE`** with the control plane (defaults: `deployai-control-plane`, `deployai`). Send the access token as **`Authorization: Bearer …`** or in the cookie named **`DEPLOYAI_WEB_ACCESS_TOKEN_COOKIE`** (default `deployai_access_token`). Middleware verifies RS256, then sets **`x-deployai-role`** and **`x-deployai-tenant`** from claims (`roles`, `tid`). Valid JWTs **override** spoofed client `x-deployai-*` headers. If a Bearer or cookie value is **sent** but **none** verify (wrong key, expired, or no recognized V1 role), the response is **401** so the request cannot fall through to forged headers alone.
  2. **Edge / reverse proxy** — set **`x-deployai-role`** and **`x-deployai-tenant`** from your IdP or gateway (no JWT on the web app).

## Pilot hardening — require tenant

Set **`DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`** on the web app so strategist **pages** and **strategist APIs** (`/api/bff/*`, `/api/internal/strategist-activity`) return **403** if **`x-deployai-tenant`** is missing or blank.

- Does **not** apply to `/admin/*` routes (different operator model).
- With JWT trust enabled, `tid` from the access token satisfies this check once middleware has run.

## `DEPLOYAI_DISABLE_DEV_STRATEGIST`

Set to **`1`** in development to **disable** the automatic `deployment_strategist` header default. Use this when testing production-like behavior locally (e.g. only JWT or only explicit headers). In **`NODE_ENV=production`**, dev injection is already impossible.

## Target (Epic 2 complete path)

First-party login and refresh flows own session cookies; the access JWT shape and claims stay aligned with the control plane. Proxy-only headers remain supported for customers that terminate SSO at the edge.

## See also

- [`tenant-provisioning.md`](./tenant-provisioning.md) — internal session mint for tests
- [`../dev-environment.md`](../dev-environment.md) — strategist dev defaults
