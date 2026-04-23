# Tenant isolation — three-layer defense (NFR23)

DeployAI stores every customer's data in one Postgres cluster. That shared-instance posture is the
PRD's Party Mode revision — separate-database-per-tenant was deemed too expensive to scale to the
public-sector customer count and too brittle when restoring multi-tenant artifacts from backup.

The consequence: tenant isolation is a **property we enforce**, not a property the infrastructure
gives us for free. Architecture §L181–184 requires three independent layers so that a defect at
any one layer does not cause a cross-tenant read.

## Layer 1 — Application (`TenantScopedSession`)

Every SQLAlchemy session against canonical memory is minted by
`deployai_tenancy.session.TenantScopedSession`:

```python
from uuid import UUID
from deployai_tenancy import TenantScopedSession

async with TenantScopedSession(tenant_id=UUID("..."), engine=engine) as session:
    result = await session.execute(select(CanonicalMemoryEvent))
```

On entry the context manager:

1. Validates `tenant_id` is a `uuid.UUID` (not a string, not `None`). Raises `MissingTenantScope` otherwise.
2. Refuses to nest inside an enclosing scope for a *different* tenant (raises `IsolationViolation`).
3. Opens a fresh `AsyncSession`, begins a transaction, and calls
   `SELECT set_config('app.current_tenant', <tid>, true)` — the parameterizable form of
   `SET LOCAL app.current_tenant = '<tid>'`.
4. Stashes `tenant_id` and `is_tenant_scoped=True` in `session.info` so
   `@requires_tenant_scope` can verify the scope at call time.

Any repository/service function that accepts an `AsyncSession` MUST be decorated:

```python
@requires_tenant_scope
async def list_events(session: AsyncSession) -> list[CanonicalMemoryEvent]:
    ...
```

A call with a raw `AsyncSession` (no `TenantScopedSession` wrapper) raises `MissingTenantScope`
*before* any SQL is issued. That keeps the stack trace pointing at the real caller rather than a
generic Postgres privilege error.

## Layer 2 — Database (Postgres RLS)

Migration `20260422_0002_tenant_rls_policies.py` attaches `tenant_rls_<table>` policies to every
canonical-memory table and `ALTER TABLE ... FORCE ROW LEVEL SECURITY`. FORCE is defense-in-depth:
with the current setup the tables are owned by the migration-runner (a superuser that has implicit
`BYPASSRLS`), so FORCE does not yet change behavior. It matters the moment ownership is transferred
to a non-superuser role (likely Story 2.4+), at which point FORCE keeps the owner subject to the
same policies everyone else is subject to.

The policy shape:

```sql
CREATE POLICY tenant_rls_canonical_memory_events
    ON public.canonical_memory_events
    USING (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid)
    WITH CHECK (tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid);
```

`current_setting('app.current_tenant', true)` returns `NULL` when the GUC is unset (fail-closed —
the `NULL = <uuid>` comparison evaluates to NULL → row filtered out). That means an accidental
raw query through an unscoped connection returns zero rows silently rather than leaking.

### The `BYPASSRLS` gotcha

Postgres superusers carry an implicit `BYPASSRLS` attribute that overrides FORCE. The migration
creates a non-superuser role `deployai_app` with `LOGIN NOINHERIT`:

```sql
CREATE ROLE deployai_app LOGIN NOINHERIT;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.<table> TO deployai_app;
```

All application traffic from control-plane MUST connect as `deployai_app` starting **Story 2.4**.
Until then, the superuser connection remains the default — policies are applied only when we
`SET SESSION AUTHORIZATION deployai_app` explicitly (done by the integration-test harness).
Story 1.10's fuzz harness attacks both paths (with and without BYPASSRLS).

## Layer 3 — Encryption (envelope pattern)

`deployai_tenancy.envelope` ships the primitives:

- `DEKProvider` protocol: `async def get_dek(tenant_id) -> bytes`.
- `InMemoryDEKProvider(environment={dev|test|ci})` — dev-only deterministic DEK derivation from
  `SHA-256(tenant_id.bytes || pepper)`. Raises `DEKUnavailable` in any other environment.
- `encrypt_field(session, *, plaintext, dek)` — wraps `pgp_sym_encrypt_bytea(plaintext, dek.hex())`.
- `decrypt_field(session, *, ciphertext, dek)` — the inverse.

Both helpers are `@requires_tenant_scope`-decorated so a raw session cannot invoke them.

**Production (`KMSEnvelopeDEKProvider`) lands Story 3.x** when AWS infra is provisioned:

- `GenerateDataKey(KeyId=<per-tenant-CMK>, KeySpec=AES_256)` mints the DEK per encryption.
- The KMS-encrypted DEK is stored alongside the ciphertext.
- `Decrypt` unwraps on read, with a bounded TTL cache to avoid per-read KMS latency.

DEK rotation per NFR76 (90-day cadence) lands in **Story 12.x**.

## What this enforces end-to-end

A cross-tenant read requires bypassing *all three* of:

- The `@requires_tenant_scope` runtime guard (raises before any SQL).
- The `tenant_rls_<table>` policy (filters rows silently, raises on writes).
- The envelope-encrypted columns (opaque without the tenant's DEK).

A defect at any one layer — a missed decorator, a dropped policy, a mis-scoped DEK — leaves the
other two intact. Story 1.10's fuzz harness attacks each layer independently.

## Scope fences (Story 1.9)

- **Real AWS KMS DEK provider** — Story 3.x.
- **DEK rotation** — Story 12.x.
- **`deployai_app` as default connection user** — Story 2.4.
- **Encrypted columns on canonical tables** (`private_annotation`, `raw_transcript_content`) —
  Epic 10 and Epic 11 when their bearing entities land. Story 1.9 ships the **mechanism**, not the
  column migrations.
- **Fuzz harness** — Story 1.10.

## Further reading

- `_bmad-output/planning-artifacts/architecture.md` §L181–184
- `docs/canonical-memory.md`
- `services/_shared/tenancy/README.md`
- NFR23 (three-layer isolation), NFR52 (fuzz CI gate), NFR76 (key rotation)
