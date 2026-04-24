# Story 2.2: Microsoft Entra ID SAML + OIDC SSO (FR71)

Status: ready-for-dev

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

- [ ] Add CP dependencies: `authlib`, `python3-saml` (verify PyPI name / maintenance; pin), `httpx` if missing, `PyJWT` or authlib’s JWT, `cryptography` for PEM keys.
- [ ] Alembic: `app_users` (or align with future naming) with `id`, `entra_sub`, `email`, `role` (enum incl. `pending_assignment`), `tenant_id` nullable FK, timestamps.
- [ ] Config surface: `Settings` in control-plane for `ENTRA_SAML_*`, `ENTRA_OIDC_*`, `JWT_*`, `REDIS_URL` (compose already has Redis; wire env in `docker-compose` + `.env.example`).
- [ ] FastAPI routers under `src/control_plane/api/routes/auth_*.py` + include in `main.py` with CORS only where needed.
- [ ] BFF: optional `apps/web` routes that proxy to CP or browser redirect to CP for OAuth (avoid CORS for cookies — prefer same-site or dedicated auth subdomain pattern as in architecture).
- [ ] Remove **header-only** dev auth in web **only** after 2-2+2-4: until then, keep `x-deployai-role` for local dev; document in `docs/auth/sso-setup.md` § “Local development.”
- [ ] Contract tests; `pytest` integration with **test Redis** (testcontainers or dev compose network).

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

_(on implementation)_

### Completion Notes List

### File List

---

**References:** `_bmad-output/planning-artifacts/architecture.md` · PRD FR71
