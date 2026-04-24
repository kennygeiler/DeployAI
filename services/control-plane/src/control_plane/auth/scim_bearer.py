"""SCIM bearer token validation (per-tenant hash in `app_tenants`)."""

from __future__ import annotations

import hashlib
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select

from control_plane.db import AppDbSession
from control_plane.domain.app_identity.models import AppTenant


def hash_scim_bearer_token(raw: str) -> str:
    """SHA-256 hex digest of the raw bearer secret (never log the raw value)."""
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


async def require_scim_tenant(
    session: AppDbSession,
    authorization: str | None = Header(default=None),
) -> AppTenant:
    if not authorization or not authorization.strip().lower().startswith("bearer "):
        raise _scim_unauthorized("Missing or invalid Authorization header")
    token = authorization[7:].strip()
    if not token:
        raise _scim_unauthorized("Empty bearer token")
    digest = hash_scim_bearer_token(token)
    r = await session.execute(select(AppTenant).where(AppTenant.scim_bearer_token_hash == digest).limit(1))
    t = r.scalar_one_or_none()
    if t is None:
        raise _scim_unauthorized("Invalid bearer token")
    return t


def _err(status: int, detail: str) -> dict[str, str | list[str]]:
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
        "status": str(status),
        "detail": detail,
    }


def _scim_unauthorized(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=_err(401, detail),
        headers={"WWW-Authenticate": "Bearer"},
    )


ScimTenant = Annotated[AppTenant, Depends(require_scim_tenant)]
