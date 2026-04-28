# Session and headers (Strategist pilot)

## Today (`apps/web`)

- **Development:** [`middleware.ts`](../../apps/web/middleware.ts) can inject `x-deployai-role: deployment_strategist`. [`getActorFromHeaders`](../../apps/web/src/lib/internal/actor.ts) mirrors that for Route Handlers when headers are missing.
- **Production / `next start`:** No role injection. Callers must send **`x-deployai-role`** (and for CP-scoped reads, **`x-deployai-tenant`**) or receive **403**.

## Pilot hardening — require tenant

Set **`DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`** on the web app so strategist **pages** and **strategist APIs** (`/api/bff/*`, `/api/internal/strategist-activity`) return **403** if **`x-deployai-tenant`** is missing or blank.

- Does **not** apply to `/admin/*` routes (different operator model).
- Use when a **reverse proxy** or **edge auth** sets `x-deployai-role` and `x-deployai-tenant` from your IdP/session until full in-app SSO (Epic 2) owns those claims.

## Target (Epic 2 complete path)

Replace header injection with **signed session / OIDC**: middleware (or server session) derives `role` and `tenantId` from the IdP token and passes them to `getActorFromHeaders` successors—**no** manual browser headers for real users.

## See also

- [`tenant-provisioning.md`](./tenant-provisioning.md) — internal session mint for tests
- [`../dev-environment.md`](../dev-environment.md) — strategist dev defaults
