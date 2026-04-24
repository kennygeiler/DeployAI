# Story 2.3: SCIM 2.0 provisioning endpoint (FR71)

Status: ready-for-dev

## Story

As a **customer IT admin**,
I want to provision and deprovision DeployAI users from Entra ID via SCIM 2.0,
so that user lifecycle is managed centrally and departures trigger automatic access revocation (FR71).

## Acceptance criteria (from [epics.md](../planning-artifacts/epics.md) §Story 2.3)

1. **RFC 7644 surface** — Implement SCIM 2.0 **Users** resource (minimum) with:
   - `POST /scim/v2/Users` — create
   - `GET /scim/v2/Users` — list (support `$filter` and `startIndex`/`count` to the degree Entra requires; return `totalResults`, `itemsPerPage`, `Resources`)
   - `GET /scim/v2/Users/{id}` — retrieve
   - `PATCH /scim/v2/Users/{id}` — partial update (Entra often uses `replace` / `add` in Operations)
   - `DELETE /scim/v2/Users/{id}` — deprovision
   - Mount under a **single router prefix** (e.g. `/scim/v2`) with correct `schemas` in every JSON body.

2. **Tenant + auth** — Each customer’s SCIM app sends a **bearer token**; validate HMAC or opaque token **scoped to one tenant** (store `scim_bearer_token_hash` per tenant in Postgres or Secrets Manager; never log raw tokens). Reject with **401** on mismatch.

3. **User mapping** — Map SCIM `userName` / `emails[primary]` / `name` to the same **app user** model introduced for Story **2-2** (`entra_sub` or SCIM `externalId` as stable id). If 2-2 schema is not merged yet, define **compatible** columns in a single migration to avoid double migrations.

4. **DELETE semantics** — Set user **`active: false` / `deactivated`**, **revoke** refresh tokens: delete Redis keys for `tenant:<tid>:session:*` for that `user_id` (full pattern in Story **2-4**; if Redis session API not shipped, implement `delete_user_sessions(tenant_id, user_id)` as a no-op with `TODO(2-4)` **only** if documented in completion notes and unit-tested contract exists).

5. **Audit** — Emit structured audit: `scim.user.provisioned|updated|deactivated` with `tenant_id`, `subject` (user id), `scim_id`, and **no PII in clear** beyond what compliance requires (hash email in audit if policy says so).

6. **Attributes** — Support: `userName`, `name.givenName`, `name.familyName`, `emails`, `active`, `roles` (map `roles` to internal V1 role **only** if product allows; else store raw and require Platform Admin to confirm — document).

7. **Tests** — Pytest with **Entra-shaped JSON fixtures** (import from files under `services/control-plane/tests/fixtures/scim/`) for create, patch, delete; assert DB state + HTTP status per RFC error model (`urn:ietf:params:scim:api:messages:2.0:Error`).

8. **Docs** — `docs/auth/scim-setup.md`: Entra SCIM app, provisioning URL, token generation, group assignment optional, troubleshooting.

## Tasks / subtasks (suggested order)

- [ ] **Prereq check:** Confirm Story **2-2** user/tenant model exists; if not, add minimal **users** + `tenants` + SCIM token columns in one Alembic (coordinate with 2-2 owner).
- [ ] Add `services/control_plane/api/routes/scim.py` (or `scim/`) with **content-type** `application/scim+json` on responses.
- [ ] Pydantic models mirroring SCIM 2.0 **User** resource + ListResponse + Error.
- [ ] Middleware/dependency: resolve **tenant** from bearer token before handler runs.
- [ ] Wire **Redis** client from settings for session revoke (or stub per AC4).
- [ ] Ruff, mypy, `pytest` unit + httpx `TestClient` integration.

## Dev notes

### Order relative to 2-2 / 2-4

- **2-2 (SSO)** and **2-3 (SCIM)** both need the **same user table** and tenant scoping. Prefer **2-2 user migration first** or a **shared branch**; do not fork two conflicting `users` schemas.
- **2-4 (session store)** defines Redis key shape; 2-3 should **import** a small `revoke_sessions_for_user` module — if 2-4 is not done, place the function in `services/_shared/tenancy` or `control_plane/auth/session.py` and implement in 2-4.

### Security

- SCIM is a **server-to-server** high-privilege path: rate limit, **IP allow list** optional config, audit every call.
- Validate **Content-Length** and reject huge bodies; Entra has documented limits.

### Standards

- [RFC 7643](https://www.rfc-editor.org/rfc/rfc7643) (resource schema) / [RFC 7644](https://www.rfc-editor.org/rfc/rfc7644) (protocol). Microsoft adds quirks — link [Azure AD SCIM](https://learn.microsoft.com/en-us/entra/identity/app-provisioning/use-scim-to-provision-users-and-groups) in docs.

## Dev Agent Record

### Agent Model Used

_(on implementation)_

### Completion Notes List

### File List

---

**References:** FR71 in PRD · `_bmad-output/planning-artifacts/architecture.md` (API + tenant isolation)
