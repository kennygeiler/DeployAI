"""Bearer-token authentication for the MCP inbound server (scope-v2 §8.4).

The MCP client presents ``Authorization: Bearer mcp_live_<hex>``. We hash
the candidate and look up an active ``tenant_api_keys`` row whose stored
``hashed_secret`` matches. Verification uses the timing-safe helper from
``control_plane.domain.app_identity.api_keys.verify_raw_key``.

Once resolved, every request carries a :class:`MCPPrincipal` with the tenant
and engagement scope baked in — every downstream resource / tool call enforces
that scope before reading rows.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated

from control_plane.domain.app_identity.api_keys import TenantApiKey, verify_raw_key
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from mcp_server.db import get_session


@dataclass(frozen=True)
class MCPPrincipal:
    """One authenticated MCP caller; bound to a tenant + engagement."""

    api_key_id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    name: str
    scopes: tuple[str, ...]

    def require_engagement(self, requested: uuid.UUID) -> uuid.UUID:
        """Assert ``requested`` matches the principal's scope, else 403."""
        if self.engagement_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="this api key has no engagement scope; tenant-wide keys are not yet supported",
            )
        if requested != self.engagement_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="engagement is out of scope for this api key",
            )
        return self.engagement_id

    def scoped_engagement(self) -> uuid.UUID:
        """Return the engagement id the principal is bound to, or 403."""
        if self.engagement_id is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="this api key has no engagement scope",
            )
        return self.engagement_id


def _parse_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.strip().lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="empty bearer credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token


async def _resolve_api_key(session: AsyncSession, raw_token: str) -> TenantApiKey:
    """Walk active rows, verifying each candidate. O(n) on active keys.

    At our scale (≤ thousands of active keys per tenant), a per-request linear
    scan over hashed_secret values is fine. Each row carries a salted hash so
    we cannot pre-filter by digest. We DO short-circuit on the first verify hit
    so the worst case is bounded by the number of revoked-key collisions.
    """
    stmt = select(TenantApiKey).where(TenantApiKey.revoked_at.is_(None))
    rows = list((await session.execute(stmt)).scalars().all())
    for row in rows:
        if verify_raw_key(raw_token, row.hashed_secret):
            return row
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="invalid or revoked api key",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def require_principal(
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: str | None = Header(default=None),
) -> MCPPrincipal:
    """FastAPI dependency: parse + verify bearer, return :class:`MCPPrincipal`."""
    token = _parse_bearer(authorization)
    row = await _resolve_api_key(session, token)
    row.last_used_at = datetime.now(UTC)
    await session.commit()
    return MCPPrincipal(
        api_key_id=row.id,
        tenant_id=row.tenant_id,
        engagement_id=row.engagement_id,
        name=row.name,
        scopes=tuple(row.scopes or ()),
    )


__all__ = ["MCPPrincipal", "require_principal"]
