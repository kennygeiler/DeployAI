# Platform account provisioning (FR70, Story 2-5)

## Endpoint

`POST /platform/accounts` — requires `Authorization: Bearer` access token whose JWT includes `platform_admin` in `roles` and `token_use: access` (see Story 2-4 / `require_platform_admin`).

Request body:

- `organization_name` (string) — display name of the new tenant
- `initial_strategist_email` (email) — first `deployment_strategist` in `app_users` for that tenant

Response: `201` with `tenant_id`, `initial_strategist_user_id`, and `created_at`.

## Errors (client-safe)

- `501` — `DEPLOYAI_TENANT_DEK_MODE=aws_kms` is set but that mode is not implemented in this build (detail: tenant encryption mode not available).
- `500` — other invariant or internal failures during provisioning; the response body is generic (no internal exception text). Check server logs for `account.provision.failed`.

## Database effects

- Inserts a row in `app_tenants` with a new random UUID, `name`, optional **null** `scim_bearer_token_hash` (SCIM is configured later; until then the SCIM API cannot resolve this tenant from a bearer hash).
- Stores **per-tenant DEK** envelope fields on `app_tenants`: `tenant_dek_ciphertext` (Base64) and `tenant_dek_key_id` (see **KMS** below).
- Inserts a row in `app_users` for the strategist with `roles` containing `deployment_strategist`.
- Before **commit**, the service counts `canonical_memory_events` for the new `tenant_id` and rolls back if non-zero. The query uses an explicit `tenant_id` filter (no reliance on RLS for this invariant).
- `account.provisioned` is logged **only after** a successful commit.

## KMS / DEK (AR4)

- `DEPLOYAI_TENANT_DEK_MODE=stub` (default): the service generates 32 random bytes, Base64-encodes them, and uses key id `stub-local`. Column names match production (`tenant_dek_ciphertext`), but the payload is **not** KMS-wrapped. No AWS calls.
- `DEPLOYAI_TENANT_DEK_MODE=aws_kms`: not implemented yet; reserved for a future change that will wrap the generated DEK with a CMK in AWS KMS.

## Local and integration tests

- Full-path tests mint a short-lived access token with `POST /internal/v1/test/session-tokens` (requires `DEPLOYAI_ALLOW_TEST_SESSION_MINT=1` and a valid `X-DeployAI-Internal-Key`). Platform APIs then use the returned `access_token` as `Authorization: Bearer`.
- Assertion of **RLS** for canonical memory uses the `deployai_app` role (not the database superuser), matching Story 1.9 isolation tests.

## Audit

The service logs `account.provisioned` with `tenant_id`, optional `actor_sub` from the JWT, and a **SHA-256** prefix of the strategist email (no clear-text email in logs).
