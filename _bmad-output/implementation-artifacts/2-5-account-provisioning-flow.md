# Story 2.5: Account provisioning flow (FR70)

Status: done

## Story

As a **Platform Admin**,
I want to provision a new account, assign the initial Deployment Strategist, and establish an empty canonical memory baseline with tenant-scoped encryption context,
so that FR70 is satisfied and each new anchor tenant goes live with isolation verified.

## Acceptance criteria (from [epics.md](../planning-artifacts/epics.md) §Story 2.5)

1. **Auth** — Caller is authenticated (Story 2-2) with **Platform Admin** (Story 2-1 `can_access` / `platform_admin`). Until 2-2 is merged, use the same **Bearer** access model as 2-4 (JWT `roles` claim) and/or a guarded internal test path documented in completion notes.

2. **API** — `POST /platform/accounts` with body `{ "organization_name": string, "initial_strategist_email": string }` (or matching contract in [architecture.md](../planning-artifacts/architecture.md)); returns the new `tenant_id` and creation metadata.

3. **Tenant** — Mint a new **UUID** for the account; create `app_tenants` row (or the canonical name table used elsewhere) with `name` = organization.

4. **KMS (AR4)** — Per-tenant **data encryption key (DEK)** generated, wrapped with the account **CMK** via **AWS KMS** envelope encryption; store only wrapped key material + `key_id` in Postgres (or Secrets Manager if that is the project pattern). **Local/dev:** pluggable “fake KMS” or minio/LocalStack only if the repo already uses it; otherwise document **stub** with `TODO` and feature flag.

5. **Canonical memory baseline** — No cross-tenant reads; for the new tenant, canonical-memory tables exist and are **empty** at provision time (or insert explicit “bootstrap” events if product requires a non-empty audit trail — document the choice).

6. **User + role** — Create or **match** `app_users` (SSO/SCIM) for `initial_strategist_email`; assign role **`deployment_strategist`** scoped to the new `tenant_id` (align 2-1 role matrix and `app_users.roles` JSON).

7. **Audit** — Emit structured `account.provisioned` (logger now; align with Epic 5 audit envelope when it lands) with **no PII in clear** beyond policy; if RFC 3161 signing exists in-repo, use it, else `TODO(Story 1-13/5)` with a single integration assertion.

8. **Tests** — **Cross-tenant guard:** new tenant cannot `SELECT` / API-read another tenant’s rows (re-use or extend **cross-tenant fuzz** patterns from Story 1-10 or add one integration test). **Integration:** full `POST /platform/accounts` → assert DB + HTTP.

9. **Docs** — `docs/platform/account-provisioning.md` (or a section in `docs/auth/sessions.md` / architecture) covering env, KMS, and local dev.

## Tasks / subtasks (suggested order)

- [x] **Contract** — Pydantic `PlatformAccountCreate` / `PlatformAccountCreated` in `control_plane/schemas/platform.py` (OpenAPI from FastAPI).
- [x] **Auth dependency** — `require_platform_admin` from `control_plane/api/routes/auth.py`.
- [x] **Service** — `provision_platform_account` in `control_plane/services/account_provision.py` (tenant + user, stub DEK, baseline check, audit log line).
- [x] **Route** — `control_plane/api/routes/platform.py`, prefix `/platform`, `POST /accounts`.
- [x] **Migrations** — `20260426_0005`: nullable `scim_bearer_token_hash`, `tenant_dek_ciphertext` / `tenant_dek_key_id` on `app_tenants`.
- [x] **KMS** — `control_plane/infra/tenant_dek.py` (stub; `aws_kms` reserved / `NotImplementedError`).
- [x] **Tests** — integration `tests/integration/test_account_provision_flow.py` (Postgres + Redis + internal mint + RLS with `deployai_app`).
- [x] **Main** — `include_router(platform_router)`.
- [x] **Docs** — `docs/platform/account-provisioning.md`.

## Dev notes

- **Depends on:** 2-1 (authz), 2-3 (`app_tenants` / `app_users`), 2-4 (JWT/Bearer for admin in tests). 2-2 (SSO) for production login, not for core API.
- **Avoid** a second `users` table; extend `app_users` and [role-matrix.md](../../docs/authz/role-matrix.md) if roles change.
- [architecture.md](../planning-artifacts/architecture.md) — tenant isolation, RLS, canonical memory.

## Dev Agent Record

### Agent Model Used

Composer (implementation)

### Debug Log References

— 

### Completion Notes List

- `app_tenants.scim_bearer_token_hash` is nullable for tenants provisioned before SCIM is configured; `require_scim_tenant` still resolves only by hash match.
- Baseline count uses an explicit `WHERE tenant_id` so the check is valid even if the app DB user bypasses RLS (e.g. superuser).
- RLS cross-tenant assertion uses the `deployai_app` role (Story 1.9 pattern).

### File List

- `services/control-plane/alembic/versions/20260426_0005_app_tenants_dek_nullable_scim.py`
- `services/control-plane/src/control_plane/domain/app_identity/models.py`
- `services/control-plane/src/control_plane/config/settings.py` (`tenant_dek_mode`)
- `services/control-plane/src/control_plane/infra/tenant_dek.py`
- `services/control-plane/src/control_plane/services/account_provision.py`
- `services/control-plane/src/control_plane/schemas/platform.py`
- `services/control-plane/src/control_plane/api/routes/platform.py`
- `services/control-plane/src/control_plane/main.py`
- `services/control-plane/pyproject.toml` (email-validator for `EmailStr`)
- `services/control-plane/tests/integration/test_account_provision_flow.py`
- `docs/platform/account-provisioning.md`

---

**References:** FR70, [epics.md](../planning-artifacts/epics.md) §2.5, AR4 in architecture
