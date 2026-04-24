# Control-plane sessions (Story 2-4, AR9)

## Overview

The control plane issues **RS256** access tokens (15-minute TTL) and stores **opaque refresh tokens** in **Redis** under a tenant-prefixed key layout. Refresh tokens rotate on each `/auth/refresh` call.

## Environment variables

| Variable | Description |
|----------|-------------|
| `DEPLOYAI_REDIS_URL` | e.g. `redis://127.0.0.1:6379/0` locally, or `rediss://…` in production (TLS). |
| `DEPLOYAI_REDIS_SSL_CA_CERTS`, `DEPLOYAI_REDIS_SSL_CERTFILE`, `DEPLOYAI_REDIS_SSL_KEYFILE` | Optional client TLS to Redis when using `rediss://` (see `ControlPlaneSettings`). |
| `DEPLOYAI_JWT_PRIVATE_KEY_PATH` | PEM path to RS256 private key (sign access tokens). **Never** commit the key. |
| `DEPLOYAI_JWT_PUBLIC_KEY_PATHS` | Comma-separated PEM paths. All listed public keys are used to **verify** (rotation / NFR76). If omitted, the public half is derived from the private key (single-key setups). |
| `DEPLOYAI_JWT_ISSUER` / `DEPLOYAI_JWT_AUDIENCE` / `DEPLOYAI_JWT_KID` | JWT standard claims. |
| `DEPLOYAI_ALLOW_TEST_SESSION_MINT` | `1`/`true` to allow `POST /internal/v1/test/session-tokens` (still requires `X-DeployAI-Internal-Key`). **Off** in production. |

Tuning (defaults match architecture):

- `DEPLOYAI_ACCESS` — not used as env name; access TTL is fixed in settings (`access_token_ttl_seconds`, default 900).
- `DEPLOYAI_REFRESH` — use code defaults: 7 days for refresh material in Redis.

## Redis key layout

- **Refresh record:** `tenant:{tenant_uuid}:session:{refresh_jti}`  
  Value: JSON `{"user_id", "tenant_id", "roles"}` with TTL 7 days.
- **JTI lookup (refresh API):** `jti:{refresh_jti}`  
  Duplicates the same JSON + TTL for O(1) refresh when the client must send `tenant_id` in the body: if the tenant in the request does not match the stored record, the API returns **403** (avoids a silent miss from building the wrong `tenant:…:session:…` key).
- **Index (for fast revoke):** `tenant:{tenant_uuid}:user:{user_id}:refresh_jtis`  
  Redis `SET` of refresh JTIs, same TTL refresh as the session keys.

`revoke_all_for_user` and the SCIM `DELETE` hook delete all `session:{jti}` keys for the user and remove the index set.

## HTTP API

- `POST /internal/v1/test/session-tokens` — (internal key + `DEPLOYAI_ALLOW_TEST_SESSION_MINT`) mints access + refresh for integration tests.
- `POST /auth/refresh` — body `{ "tenant_id": "<uuid>", "refresh_token": "<opaque>" }` (rotates refresh).
- `POST /auth/logout` — same body; looks up the refresh via `jti:{jti}` (like refresh). Wrong `tenant_id` → **403**; unknown refresh → **401**.
- `POST /auth/sessions/revoke-all/{user_id}` — **Bearer** access token with `platform_admin` in `roles`; revokes all refresh keys for that user in the **token’s** tenant.

Access tokens are **not** stored in Redis; only refresh metadata is.

## JWT rotation (NFR76)

- Deploy a **second** public key PEM in `DEPLOYAI_JWT_PUBLIC_KEY_PATHS` when rotating; both old and new public keys are accepted during verification.
- Point `DEPLOYAI_JWT_PRIVATE_KEY_PATH` at the new signing key; after one access-TTL window, old keys can be removed from the public list.

## See also

- [scim-setup.md](scim-setup.md) — SCIM calls `revoke_sessions_for_user` on deprovision, which uses the same Redis layout.
