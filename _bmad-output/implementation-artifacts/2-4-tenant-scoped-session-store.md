# Story 2.4: Tenant-scoped session store (AR9)

Status: ready-for-dev

## Story

As a **platform engineer**,
I want signed-JWT session issuance and Redis-backed refresh with tenant-prefixed keys and TLS 1.3 in transit,
so that sessions scale across services, are revocable on kill-switch, and never leak cross-tenant (AR9).

## Acceptance criteria (from [epics.md](../planning-artifacts/epics.md) §Story 2.4)

1. **JWT** — For authenticated users (Story 2-2 to wire full SSO; this story can ship the library + routes with test harness and stub IdP as needed), every **access** JWT payload includes at least:  
   `sub` (user id), `tid` (tenant id), `roles` (list), `iat`, `exp`, `jti` (or equivalent claim plan documented if product uses `session_id` + `jti` split). Tokens are signed with **RS256**; private key material is **not** in git (use env path or **AWS KMS** / Secrets Manager for prod-shaped wiring).

2. **Refresh in Redis** — Refresh tokens (random secret or JTI) are stored in Redis at  
   `tenant:{tenant_uuid}:session:{jti}` (see also Story 2-2/2-3 epic text: `tenant:<uuid>:session:` prefix) with **TTL = 7 days**; value **must** embed or reference `user_id` and `tenant_id` so `revoke_sessions_for_user` can find keys.

3. **Access TTL** — Access token **TTL 15 minutes** (align with architecture.md).

4. **Transport** — In production, Redis clients use **TLS 1.3**; local compose may use plain `redis://` with explicit `REDIS_URL` in `.env` (document secure vs dev split). mTLS/ACM per epic is a **deployment** concern: surface `REDIS_URL`, `REDIS_CLIENT_CERT`, `REDIS_CLIENT_KEY`, `REDIS_CA_CERTS` in Settings when `rediss://` is used so ops can meet “ACM-managed” without hard-coding AWS SDK in unit tests.

5. **Logout** — `POST /auth/logout` invalidates the **current** refresh token (from cookie or body—document contract) and removes matching Redis state.

6. **Admin revoke** — `POST /auth/sessions/revoke-all/{user_id}` (Platform **Admin** only) deletes **all** session keys for that user **within the caller’s tenant** and emits a structured **audit** log line (and optional future `audit_events` envelope when Epic 5 schema lands).

7. **NFR76 / key rotation** — Sign keys rotate on a **≤ 180 day** policy: document and implement a **KMS- or file-based** rotation path (e.g. `JWT_KID` + JWKS or multi-key verify) so prod can swap keys without double downtime; at minimum **read** new key from env/Secrets and prefer **verify** with multiple public keys if old tokens still in flight for one access TTL.

8. **2-3 follow-through** — Replace the current **no-op** in `control_plane.auth.session_revoke.revoke_sessions_for_user` (Story 2-3) with a real implementation that **deletes** the relevant Redis keys (same pattern as `DELETE /scim/v2/Users/...` expectations). **Unit and integration tests** must assert keys are removed.

9. **Tests** — `pytest` with **Testcontainers Redis** (or in-memory `fakeredis` for pure unit) + integration for issue → refresh → logout and revoke-all; no cross-tenant key reads.

10. **Docs** — Add or extend `docs/auth/sessions.md` (or a section in `docs/auth/sso-setup.md` if you prefer a single runbook) covering env vars, key rotation, and Redis key layout.

## Tasks / subtasks (suggested order)

- [ ] **Design key layout** (AC: 2, 6, 8) — Decide and document: primary key `tenant:{tid}:session:{jti}`; optional **index** set `tenant:{tid}:user:{user_id}:jtis` (SET of jtis) with **same TTL** as longest-lived refresh, or use **SCAN** in MVP with documented complexity limit.
- [ ] **Settings** — Extend control-plane `Settings` / env: `REDIS_URL`, optional TLS file paths, `JWT_PRIVATE_KEY` / `JWT_PUBLIC_KEY` paths or `JWT_*` from Secrets, `ACCESS_TOKEN_TTL`, `REFRESH_TOKEN_TTL`, `JWT_ISSUER`, `JWT_AUDIENCE` as needed.
- [ ] **Redis client** — Async Redis driver (`redis[asyncio]` 5.x or `redis.asyncio`) compatible with `REDIS_URL` in compose; connection lifecycle one **pool per process**; prefix enforcement helper in `control_plane/tenancy/redis_keys.py` or `control_plane/infra/redis.py`.
- [ ] **JWT** — RS256 sign/verify module (`control_plane/auth/jwt_tokens.py`); clock skew tolerance; JTI for refresh; multi-key **verify** list for rotation (AC 7).
- [ ] **Session service** — Issue access+refresh, validate refresh, persist refresh, rotate on refresh, delete on logout, **revoke all** for user (admin + SCIM hook).
- [ ] **Routes** — `POST /auth/logout`, `POST /auth/refresh` (if not only in 2-2, coordinate), `POST /auth/sessions/revoke-all/{user_id}` with **Authz** guard using Story **2-1** `can_access` / `platform_admin` (same pattern as other internal routes).
- [ ] **Wire 2-3** — `revoke_sessions_for_user(tenant_id, user_id)` calls Redis (same as revoke-all scope).
- [ ] **Main** — Include new routers; ensure OpenAPI tags clear.
- [ ] **Tests** — Unit (crypto, paths, key rotation); integration (Redis container), SCIM delete still passes with Redis assertion if feasible.
- [ ] **Docs** — `docs/auth/sessions.md` (or agreed location).

## Dev notes

### Order relative to 2-2 and 2-3

- **Story 2-2 (SSO)** is still the IdP + cookie surface; this story (2-4) is the **durable** session layer. If 2-2 is not ready, **stub** `POST /auth/login` for tests with a `DEPLOYAI_TEST_AUTH` flag **only in tests** (not prod defaults), or use internal-only fixture routes behind `X-DeployAI-Internal-Key`—pick one and document. Do **not** block 2-4 on Entra; block **E2E** on 2-2+2-4.
- **Story 2-3 (SCIM)** already calls `revoke_sessions_for_user` on user DELETE. Implementing 2-4 **replaces the no-op**; keep the function signature and tests added in 2-3.
- [architecture.md](../planning-artifacts/architecture.md) §Caching / Auth: Redis `tenant:<uuid>:` prefix, TLS, JWT 15m / 7d refresh.

### Control-plane surface today

- `services/control-plane/src/control_plane/auth/session_revoke.py` — **TODO(2-4)**.
- `infra/compose/docker-compose.yml` — **Redis 7** and `REDIS_URL` for control-plane.
- `services/control-plane/src/control_plane/main.py` — only health + internal schema + SCIM; auth routes to be added.

### Security and compliance

- Never log full refresh token or private key; audit events should not include PII in clear.
- `revoke-all` and SCIM **must** validate **tenant** scoping: a caller cannot pass another tenant’s `user_id` and delete keys in another prefix.

### Project structure (align with existing)

- `control_plane/api/routes/auth.py` (or `sessions.py`) and small `control_plane/auth/` modules for JWT + Redis.
- Reuse `control_plane.db` and `app_identity` for user existence checks where required.

## Dev Agent Record

### Agent Model Used

_(on implementation)_

### Debug Log References

### Completion Notes List

### File List

---

**References:** AR9 in [architecture.md](../planning-artifacts/architecture.md) (Authentication & Session, Redis); Story 2-3 [2-3-scim-2-0-provisioning-endpoint.md](2-3-scim-2-0-provisioning-endpoint.md); [epics.md](../planning-artifacts/epics.md) §2.4
