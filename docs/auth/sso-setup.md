# Microsoft Entra ID SSO (FR71) — control plane (Story 2-2 / Epic 2)

## Supported: OpenID Connect (Entra v2, PKCE)

Use an **Entra ID app registration** (or enterprise application) with the **OpenID Connect** sign-in experience. The control plane uses the authorization code flow with **PKCE**, validates `id_token` signatures with the issuer **JWKS**, and issues the same **Redis-backed refresh + RS256 access** session as the internal test mint (Story 2-4).

### Environment variables (control plane)

| Variable | Required | Purpose |
| -------- | -------- | ------- |
| `DEPLOYAI_OIDC_ISSUER` | Yes | Issuer **v2.0** base, e.g. `https://login.microsoftonline.com/<directory-tenant-id>/v2.0` (must serve `/.well-known/openid-configuration`). |
| `DEPLOYAI_OIDC_CLIENT_ID` | Yes | Application (client) ID from Entra. |
| `DEPLOYAI_OIDC_CLIENT_SECRET` | Yes | Confidential client secret from Entra. |
| `DEPLOYAI_OIDC_REDIRECT_URI` | Yes | Must match Entra’s **Web** redirect URI, e.g. `https://<control-plane-host>/auth/oidc/callback`. |
| `DEPLOYAI_JWT_PRIVATE_KEY_PATH` / `DEPLOYAI_JWT_PUBLIC_KEY_PATHS` | Yes (prod) | RS256 key material for access JWTs. |
| `DEPLOYAI_REDIS_URL` | Yes | Refresh token storage. |
| `DEPLOYAI_SESSION_ACCESS_COOKIE` | No (default `dep_access`) | HttpOnly access cookie on callback. |
| `DEPLOYAI_SESSION_REFRESH_COOKIE` | No (default `dep_refresh`) | HttpOnly refresh (opaque JTI) cookie on callback. |

### Entra app registration (summary)

1. **App registrations** → New registration → name, account type, **Web** redirect URI = `https://<host>/auth/oidc/callback`.
2. **Certificates & secrets** → New client secret; store in `DEPLOYAI_OIDC_CLIENT_SECRET`.
3. **Overview** → copy **Application (client) ID** → `DEPLOYAI_OIDC_CLIENT_ID`.
4. **Directory (tenant) ID** → build issuer: `https://login.microsoftonline.com/<tenant-id>/v2.0` → `DEPLOYAI_OIDC_ISSUER`.
5. **API permissions** (if calling Graph): add and grant admin consent as needed. Sign-in + OpenID is enough for basic profile/`sub`.

### User flow

- Browser: `GET /auth/login` (redirects to `/auth/oidc/login` when OIDC is configured) → Microsoft sign-in → `GET /auth/oidc/callback?code&state=...` → JIT `app_users` by `entra_sub`, `issue_tokens`, JSON + HttpOnly cookies.
- First-time users are placed in the system **SSO pending** tenant with role `pending_assignment` until a Platform Admin assigns a real tenant and role (or SCIM provisions them elsewhere).
- **Refresh:** `POST /auth/refresh` with `tenant_id` + `refresh_token` (body or copy from `dep_refresh` cookie in same-site clients).

## SAML 2.0

`GET /auth/saml/login` and `POST /auth/saml/acs` are reserved for a future **SAML 2.0 SP** implementation. They currently return **501** with a pointer to this document and the OIDC path. For Entra, **OIDC is the supported path** in this release.

## Other surfaces

- **SCIM 2-0** — user provisioning; see [scim-setup.md](scim-setup.md) and Story 2-3.
- **Web (Next.js)** — local dev may still use `x-deployai-tenant` / `x-deployai-role`; production browser sessions should use the control-plane cookies or bearer access tokens as wired by the web app in a later story.

**Related:** [role-matrix](../authz/role-matrix.md) · [sprint status](../../_bmad-output/implementation-artifacts/sprint-status.yaml)
