"""Exception hierarchy for tenancy violations.

All custom exceptions inherit from :class:`TenancyError` so callers can ``except
TenancyError`` to catch any isolation-related failure without coupling to the
specific subclass.
"""

from __future__ import annotations


class TenancyError(Exception):
    """Base class for all tenancy-related errors."""


class MissingTenantScope(TenancyError):  # noqa: N818 — domain-correct name (scope is the concept, not an "error").
    """Raised when a tenant-scoped operation is attempted without a scope.

    Triggers:

    * ``TenantScopedSession`` entered with ``tenant_id=None`` or a non-UUID value.
    * ``@requires_tenant_scope``-decorated function called with a session whose
      ``session.info["is_tenant_scoped"]`` is absent or falsy.
    """


class IsolationViolation(TenancyError):  # noqa: N818 — "violation" reads naturally; Error suffix would be redundant.
    """Raised when a caller attempts to cross tenant boundaries in-process.

    Triggers:

    * Nested ``TenantScopedSession`` context for a different tenant id than the
      enclosing scope.
    * Future: any raw SQL executed through a tenant-scoped session that
      references a tenant other than the current scope (enforced by Story 1.10
      fuzz harness).
    """


class DEKUnavailable(TenancyError):  # noqa: N818 — reads as a state ("unavailable"), not an action.
    """Raised when a Data Encryption Key cannot be provided.

    Triggers:

    * ``InMemoryDEKProvider`` constructed outside ``ENVIRONMENT in {dev,test}``.
    * Future (Story 3.x): AWS KMS ``Decrypt`` call fails or credentials missing.
    """
