# Story 2.4: Tenant-scoped session store (AR9)

Status: done

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

- [x] **Key layout** — `tenant:{tid}:session:{jti}`, per-user set `tenant:{tid}:user:{uid}:refresh_jtis`, and `jti:{jti}` for refresh tenant mismatch (403).
- [x] **Settings** — `control_plane/config/settings.py` (`DEPLOYAI_*` for Redis, JWT paths, `allow_test_session_mint`).
- [x] **Redis** — `control_plane/infra/redis_client.py` (async, optional TLS for `rediss://`).
- [x] **JWT** — `control_plane/auth/jwt_tokens.py` (RS256, multi-PEM verify, leeway 60s).
- [x] **Session service** — `control_plane/auth/session_service.py` (issue, refresh rotate, logout, revoke-all).
- [x] **Routes** — `control_plane/api/routes/auth.py` + internal mint `api/routes/internal_session.py` (`require_platform_admin` on revoke-all; JWT `roles` claim).
- [x] **2-3** — async `revoke_sessions_for_user` → `revoke_all_for_user` (SCIM `await`).
- [x] **Main** — auth + internal session routers.
- [x] **Tests** — unit JWT + session_revoke; integration Redis (testcontainers) + SCIM w/ fakeredis patch.
- [x] **Docs** — `docs/auth/sessions.md`

## Dev notes

### Order relative to 2-2 and 2-3

- **Internal mint:** `POST /internal/v1/test/session-tokens` with `X-DeployAI-Internal-Key` + `DEPLOYAI_ALLOW_TEST_SESSION_MINT=1` issues tokens for tests (2-2 SSO to replace in prod).
- **SCIM** calls `await revoke_sessions_for_user`; SCIM integration uses **fakeredis** patched on `session_service.get_async_redis` so no real Redis is required in that test module.

## Dev Agent Record

### Agent Model Used

Composer (default), Apr 2026

### Completion Notes List

- Refresh body contract: `tenant_id` + `refresh_token` (opaque JTI) for `/auth/refresh` and `/auth/logout`.
- `jti:{jti}` duplicate blob ensures wrong `tenant_id` in refresh returns 403, not 401.
- mTLS: use `rediss://` and `DEPLOYAI_REDIS_SSL_*` file paths; document in `docs/auth/sessions.md`.

### File List

- `services/control-plane/pyproject.toml` (redis, PyJWT, pydantic-settings, dev: fakeredis)
- `services/control-plane/src/control_plane/config/settings.py`
- `services/control-plane/src/control_plane/infra/redis_client.py`
- `services/control-plane/src/control_plane/infra/__init__.py`
- `services/control-plane/src/control_plane/auth/session_keys.py`
- `services/control-plane/src/control_plane/auth/jwt_tokens.py`
- `services/control-plane/src/control_plane/auth/session_service.py`
- `services/control-plane/src/control_plane/auth/session_revoke.py`
- `services/control-plane/src/control_plane/api/routes/auth.py`
- `services/control-plane/src/control_plane/api/routes/internal_session.py`
- `services/control-plane/src/control_plane/api/routes/scim.py` (async revoke)
- `services/control-plane/src/control_plane/main.py`
- `services/control-plane/tests/unit/test_jwt_roundtrip.py`
- `services/control-plane/tests/unit/test_session_revoke.py`
- `services/control-plane/tests/integration/test_session_store_flow.py`
- `services/control-plane/tests/integration/test_scim_flow.py`
- `docs/auth/sessions.md`

---

**References:** AR9 in [architecture.md](../planning-artifacts/architecture.md) (Authentication & Session, Redis); Story 2-3 [2-3-scim-2-0-provisioning-endpoint.md](2-3-scim-2-0-provisioning-endpoint.md); [epics.md](../planning-artifacts/epics.md) §2.4
