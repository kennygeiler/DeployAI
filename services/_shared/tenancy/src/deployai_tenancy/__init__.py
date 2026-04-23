"""DeployAI tenancy primitives — source of truth for three-layer NFR23 isolation.

This package encodes the three independent layers of DeployAI's tenant-isolation
posture per architecture §L181-184:

1. **Application layer** — ``TenantScopedSession`` context manager injects the
   tenant scope into every SQLAlchemy session.
2. **Database layer** — ``SET LOCAL app.current_tenant`` feeds the Postgres
   Row-Level Security (RLS) policies created in migration
   ``20260422_0002_tenant_rls_policies.py``.
3. **Encryption layer** — ``envelope.encrypt_field`` / ``envelope.decrypt_field``
   + per-tenant DEK (``DEKProvider`` protocol + ``InMemoryDEKProvider`` for
   dev/test; AWS-KMS-backed provider deferred to Story 3.x).

See ``docs/security/tenant-isolation.md`` for the architectural rationale and
``docs/canonical-memory.md`` for the canonical schema those primitives protect.
"""

from __future__ import annotations

from deployai_tenancy.decorators import requires_tenant_scope
from deployai_tenancy.envelope import (
    DEKProvider,
    InMemoryDEKProvider,
    decrypt_field,
    encrypt_field,
)
from deployai_tenancy.errors import (
    DEKUnavailable,
    IsolationViolation,
    MissingTenantScope,
    TenancyError,
)
from deployai_tenancy.session import (
    TENANT_ID_KEY,
    TENANT_SCOPED_KEY,
    TenantScopedSession,
    current_tenant,
)

__all__ = [
    "TENANT_ID_KEY",
    "TENANT_SCOPED_KEY",
    "DEKProvider",
    "DEKUnavailable",
    "InMemoryDEKProvider",
    "IsolationViolation",
    "MissingTenantScope",
    "TenancyError",
    "TenantScopedSession",
    "current_tenant",
    "decrypt_field",
    "encrypt_field",
    "requires_tenant_scope",
]
