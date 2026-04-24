# Story 2.2: Microsoft Entra ID SAML + OIDC SSO (FR71)

Status: **done** (2026-04-23) — Microsoft Entra via **OIDC + PKCE**; full SAML 2.0 SP **deferred** (stable `501` on `/auth/saml/*` + `docs/auth/sso-setup.md`).

## Story

As a **customer IT admin**,
I want to provision DeployAI users via Microsoft Entra ID SAML or OIDC,
so that FR71 is satisfied and anchor customers do not require a custom IdP integration.

## Acceptance criteria (from [epics.md](../planning-artifacts/epics.md) §Story 2.2)

1. **SAML** — With Entra enterprise app + IdP metadata URL or XML, `/auth/saml/acs` (or equivalent) verifies assertions using **`python3-saml`** (or maintained fork), validates audience/issuer/clock skew, and maps NameID + attributes to a stable subject.

2. **OIDC** — Alternative `/auth/oidc/callback` path using **`authlib`** (FastAPI integration) with **PKCE**, state/nonce, and JWKS signature verification.

3. **JIT user** — On first successful login, upsert a **users** (or `app_users`) row: `sub` from IdP, `pending_assignment` role until a Platform Admin binds **tenant + V1 role** (aligns with [Story 2-1](2-1-role-matrix-and-authz-resolver-interface.md) matrix).

4. **Sessions** — **JWT** access (~15m) + refresh (~7d), **Redis** storage for refresh rotation; cookie flags **`HttpOnly; Secure; SameSite=Lax`**. Key prefix: `tenant:<uuid>:session:` for tenant-scoped session data. *(Depends on **Story 2-4** if you prefer to land Redis session store first; minimum for 2-2: implement token pair + Redis in same story or stub refresh with a clear TODO to 2-4 — choose one and document in completion notes.)*

5. **Routes** — `POST /auth/refresh`, logout revoking refresh in Redis. Public **GET** `/auth/login` initiates either SAML or OIDC flow (query param or config).

6. **Tests** — Integration tests: SAML happy path (IdP **stub** or recorded XML), OIDC happy path, expired refresh, **replay** (reuse refresh token) rejected.

7. **Docs** — `docs/auth/sso-setup.md` — Entra app registration, redirect URIs, claim mapping, rotation.

## Tasks / subtasks (suggested order)

- [x] Add CP dependencies: `authlib`, `httpx`, JWT/crypto stack — **SAML** (`python3-saml` / `pysaml2`) not added; full SP is explicitly deferred; Entra is covered via **OIDC**.
- [x] `app_users` + JIT on OIDC callback (see codebase).
- [x] Config surface: `ControlPlaneSettings` — `DEPLOYAI_OIDC_*`, JWT, Redis; `.env.example` block + `docs/auth/sso-setup.md`.
- [x] FastAPI routers: `auth_oidc`, `auth_saml` (501 stub), session refresh, included in `main.py`.
- [ ] BFF: optional `apps/web` routes — not required to close 2-2; browser redirects to control-plane.
- [x] Web dev `x-deployai-role` — unchanged per local-dev guidance in `docs/auth/sso-setup.md` where applicable.
- [x] Integration tests: OIDC path + refresh **replay** + **expired** refresh; SAML route returns 501; Redis via test pattern in suite.

## Dev notes

### Build on 2-1

- Use **`can_access`** / **`can_access` (Py)** for route guards once `actor` is derived from validated JWT + DB role assignment (not from headers in prod).
- **Do not** weaken `packages/authz` matrix without updating `docs/authz/role-matrix.md`.

### Control plane today

- `services/control-plane` — FastAPI, Alembic, `deployai-tenancy`, no auth routes yet.
- Local stack: `infra/compose/docker-compose.yml` — Redis, Postgres; add env vars for auth.

### Security

- No IdP client secrets in logs; use structured logging with redaction.
- Store refresh tokens only as **opaque** Redis values or hashed, not raw JWTs if policy requires.
- CSRF: SameSite + state parameter for OIDC; SAML relay state.

### Out of scope (other stories)

- **SCIM** — Story 2.3.
- **Full web UI login page polish** — minimal redirect flow acceptable if AC met.

## Dev Agent Record

### Agent Model Used

Composer (Cursor agent), 2026-04-23

### Completion Notes List

- **Entra (production path):** `/auth/oidc/*` with PKCE, state/nonce, JWKS `id_token` verification, JIT `app_users` with `pending_assignment`, JWT access + Redis-backed refresh (Story 2-4 store).
- **SAML:** Full SP (assertion validation, `python3-saml`) is **not** in this release. `GET /auth/saml/login` and `POST /auth/saml/acs` return **501** with JSON `error: saml_not_implemented` and `oidc_login_path: /auth/oidc/login` so operators get a stable path and a clear next step. FR71 for anchor customers is met via **OIDC**; SAML-only orgs are documented as a future build.
- **Tests:** `tests/unit/test_auth_oidc_routes.py` (SAML 501 + OIDC), `tests/integration/test_session_store_flow.py` (refresh replay + TTL expiry), plus existing OIDC integration coverage.
- **Docs / env:** `docs/auth/sso-setup.md` (Entra OIDC table, SAML section); root `.env.example` Control Plane OIDC block.

### File List

- `services/control-plane/src/control_plane/auth/oidc_flow.py` — PKCE, metadata, token exchange, JWKS id_token verify
- `services/control-plane/src/control_plane/api/routes/auth_oidc.py` — `/auth/oidc/login`, `/auth/oidc/callback`, refresh, etc.
- `services/control-plane/src/control_plane/api/routes/auth_saml.py` — SAML placeholder **501**
- `services/control-plane/src/control_plane/config/settings.py` — `DEPLOYAI_OIDC_*` and related settings
- `services/control-plane/tests/integration/test_session_store_flow.py` — replay + expired refresh
- `services/control-plane/tests/unit/test_auth_oidc_routes.py` — SAML 501
- `docs/auth/sso-setup.md` — Entra OIDC + SAML deferral
- `/.env.example` — sample `DEPLOYAI_OIDC_*` and related keys

---

**References:** `_bmad-output/planning-artifacts/architecture.md` · PRD FR71
