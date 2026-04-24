# RLS alignment (tenant + role GUCs)

## Current state (Story 1.9 + Epic 2.1)

- **`SET LOCAL app.current_tenant`** — set by `TenantScopedSession` in `services/_shared/tenancy` for every transaction touching canonical memory. RLS policies use it in `20260422_0002_tenant_rls_policies.py` (`USING` / `WITH CHECK` on `tenant_id`).
- **`SET LOCAL app.current_role`** — optional **keyword** argument `app_role=` on `TenantScopedSession` (Epic 2.1). Valid values are the V1 role strings (`platform_admin`, `customer_admin`, …). Intended for **future** or **supplementary** policies (e.g. read-only vs write) that combine tenant + role.

## Policy evolution

Story 1.9 used **tenant-only** predicates. Per-role DML rules (e.g. restricting `UPDATE`/`DELETE` on `schema_proposals` to `platform_admin`) are **not** all encoded in SQL in Epic 2.1; application-layer `can_access` is authoritative for HTTP surfaces. When a migration adds a second policy on a table, it must still preserve tenant isolation and pass `tests/integration/test_tenant_isolation.py` + fuzz harnesses.

## Verification

- Integration tests: `SELECT current_setting('app.current_tenant', true)` and, when `app_role` is passed, `current_setting('app.current_role', true)` — see `services/_shared/tenancy/tests/`.

## References

- [services/control-plane/alembic/versions/20260422_0002_tenant_rls_policies.py](../../services/control-plane/alembic/versions/20260422_0002_tenant_rls_policies.py)
- [services/_shared/tenancy/src/deployai_tenancy/session.py](../../services/_shared/tenancy/src/deployai_tenancy/session.py)
