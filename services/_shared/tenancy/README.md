# deployai-tenancy

Source of truth for DeployAI's three-layer tenant-isolation contract (NFR23).

## What it exports

- `TenantScopedSession(tenant_id, engine)` — async context manager that opens a
  SQLAlchemy `AsyncSession` with `SET LOCAL app.current_tenant = <tenant_id>`
  injected inside the transaction, so Postgres RLS policies `tenant_rls_<table>`
  filter transparently.
- `@requires_tenant_scope` — decorator for async repository/service functions
  that asserts the first `AsyncSession` arg was minted by `TenantScopedSession`.
  Raises `MissingTenantScope` at call-site before any SQL is issued.
- `encrypt_field` / `decrypt_field` — pgcrypto `pgp_sym_encrypt_bytea` /
  `pgp_sym_decrypt_bytea` helpers that take a per-tenant DEK.
- `DEKProvider` Protocol + `InMemoryDEKProvider` for dev/test.
  `KMSEnvelopeDEKProvider` (AWS KMS-backed) is deferred to Story 3.x.

## Consuming from another service

Declare the package as an editable path dep in the consumer's `pyproject.toml`:

```toml
dependencies = [
  "deployai-tenancy",
]

[tool.uv.sources]
deployai-tenancy = { path = "../_shared/tenancy", editable = true }
```

Then `uv sync` from the consumer directory.

## Why a package, not a module

Epic AC text says "single source of truth for TenantScopedSession and exports a
`@requires_tenant_scope` decorator". A Python package published (even internally
as a path dep) is the only shape where multiple services actually import from
one place — a bare `.py` file would force each service to copy-paste or fragile
sys.path hacks.

## Further reading

- `docs/security/tenant-isolation.md` — three-layer defense rationale.
- `docs/canonical-memory.md` — the canonical tables these primitives protect.
- `_bmad-output/planning-artifacts/architecture.md` §L181-184 — NFR23 design.
