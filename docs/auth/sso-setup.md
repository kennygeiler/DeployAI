# Microsoft Entra ID SSO (FR71) — current state and roadmap (Story 2-2)

## Current state (control plane)

- **OIDC (Entra v2, PKCE).** When `DEPLOYAI_OIDC_ISSUER`, `DEPLOYAI_OIDC_CLIENT_ID`, `DEPLOYAI_OIDC_CLIENT_SECRET`, and `DEPLOYAI_OIDC_REDIRECT_URI` are all set, `GET /auth/login` (→ `/auth/oidc/login`) starts the code flow; `GET /auth/oidc/callback` exchanges the code, verifies the `id_token` against the issuer JWKS, **upserts** `app_users` (by `entra_sub`), **mints Redis + RS256 access/refresh** (`issue_tokens`), returns JSON (`access_token`, `refresh_token` JTI, `user_id`, `tenant_id`, …), and sets **HttpOnly** cookies `dep_access` / `dep_refresh` (names overridable via `DEPLOYAI_SESSION_ACCESS_COOKIE` / `DEPLOYAI_SESSION_REFRESH_COOKIE`). New users land in the system **SSO pending** tenant with role `pending_assignment` until a Platform Admin assigns a real tenant + role.
- **Sessions:** RS256 access JWT + Redis refresh (`POST /auth/refresh`, `POST /auth/logout`, `POST /auth/sessions/revoke-all/{user_id}`) per Story 2-4. Internal tests may mint short-lived tokens via `POST /internal/v1/test/session-tokens` with `X-DeployAI-Internal-Key` and `DEPLOYAI_ALLOW_TEST_SESSION_MINT=1`.
- **Web UI (Next.js):** dev builds still honor `x-deployai-tenant` / `x-deployai-role` (see [role-matrix](../../authz/role-matrix.md)). Production **IdP-issued** cookies and `/auth/callback` flows are **not** shipped in this pass.
- **SCIM:** per-tenant `POST/GET/… /scim/v2/Users` with bearer + `app_tenants.scim_bearer_token_hash` (Story 2-3) — operational once Entra points at the DeployAI base URL and a SCIM token is set on the tenant.

## Planned: SAML 2.0 and OIDC (Entra enterprise app)

1. **Entra** enterprise application: SAML 2.0 and/or OIDC (PKCE) registration with `python3-saml` / `authlib` in the control plane (or a thin BFF in `apps/web`), consuming IdP metadata and configuring ACS/callback URLs.
2. **JIT user:** first login creates/updates an `app_users` row; default `pending_assignment` (or `roles: []`) until a **Platform Admin** assigns tenant + `deployment_strategist` in product flows (SCIM and/or platform APIs).
3. **Cookies:** `HttpOnly; Secure; SameSite=Lax` for refresh; access token in memory or short cookie per security review.

This document will gain exact Entra portal screenshots, reply URLs, and claim rules when Story 2-2 is implemented in code. Until then, use **test mint** + **SCIM** for end-to-end tenant/user plumbing.
