"""Centralized internal-API auth dependencies (pilot-refresh A4).

Two FastAPI dependencies replace the twelve copy-pasted ``require_internal``
definitions that had accumulated across ``api/routes/``:

- :func:`require_internal` — behavior-preserving port of the copies: accepts
  only the global ``X-DeployAI-Internal-Key`` shared secret. Used by admin /
  ops routes and as the bootstrap gate for minting tenant-scoped tokens.
- :func:`require_tenant_scoped` — tenant-aware gate for routes that take a
  ``tenant_id`` query param. Accepts either a per-tenant service token
  (``internal_service_tokens`` row; the token's tenant MUST match the
  ``tenant_id`` param or the request is rejected with 403) or, during the
  deprecation window, the legacy global key — with a structured warning per
  use so operators can find the remaining legacy callers and migrate them.

The legacy key is compared with ``hmac.compare_digest`` (see
``config/internal_api.py``); service tokens are matched by SHA-256 digest
lookup (see ``domain/app_identity/service_tokens.py``).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import Header, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import AppDbSession
from control_plane.domain.app_identity.service_tokens import (
    InternalServiceToken,
    hash_service_token,
)

_log = logging.getLogger(__name__)

INTERNAL_KEY_HEADER = "X-DeployAI-Internal-Key"


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias=INTERNAL_KEY_HEADER),
) -> None:
    """Admin gate: the global internal key only (no tenant-scoped tokens).

    Behavior-preserving centralization of the definitions that used to live in
    twelve route modules. Routes that scope by tenant should prefer
    :func:`require_tenant_scoped`.
    """
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


@dataclass(frozen=True)
class InternalPrincipal:
    """Who authenticated on an internal route.

    ``tenant_id`` is ``None`` for the legacy global key (tenant-unbound) and
    the token's tenant for a per-tenant service token.
    """

    mode: str  # "legacy_global_key" | "tenant_service_token"
    tenant_id: uuid.UUID | None
    token_id: uuid.UUID | None


async def _resolve_service_token(
    session: AsyncSession,
    raw_key: str,
) -> InternalServiceToken | None:
    digest = hash_service_token(raw_key)
    return (
        await session.execute(
            select(InternalServiceToken).where(
                InternalServiceToken.hashed_key == digest,
                InternalServiceToken.revoked_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def require_tenant_scoped(
    session: AppDbSession,
    tenant_id: Annotated[uuid.UUID, Query()],
    x_deployai_internal_key: Annotated[
        str | None,
        Header(alias=INTERNAL_KEY_HEADER),
    ] = None,
) -> InternalPrincipal:
    """Tenant-aware internal gate for routes that scope by ``tenant_id`` query param.

    Resolution order:

    1. Legacy global key → allowed for any tenant (deprecation path); emits a
       structured warning per use so remaining callers can be migrated.
    2. Per-tenant service token → the ``tenant_id`` query param must equal the
       token's tenant, else 403. Revoked/unknown tokens → 401.
    """
    if not x_deployai_internal_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )

    if verify_internal_key(x_deployai_internal_key):
        _log.warning(
            "internal_auth.legacy_global_key_used",
            extra={
                "auth_mode": "legacy_global_key",
                "requested_tenant_id": str(tenant_id),
            },
        )
        return InternalPrincipal(mode="legacy_global_key", tenant_id=None, token_id=None)

    token = await _resolve_service_token(session, x_deployai_internal_key)
    if token is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )
    if token.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_id is out of scope for this service token",
        )
    return InternalPrincipal(
        mode="tenant_service_token",
        tenant_id=token.tenant_id,
        token_id=token.id,
    )


__all__ = [
    "INTERNAL_KEY_HEADER",
    "InternalPrincipal",
    "require_internal",
    "require_tenant_scoped",
]
