"""Map JWT access claims to deployai_authz :class:`AuthActor`."""

from __future__ import annotations

from typing import Annotated

from deployai_authz import AuthActor
from deployai_authz.resolver import V1Role
from fastapi import Depends, HTTPException, status

from control_plane.api.routes.auth import bearer_access_claims

# Strict platform roles first (highest authority wins for matrix checks with multi-role tokens).
_V1_ORDER: tuple[V1Role, ...] = (
    "platform_admin",
    "customer_admin",
    "deployment_strategist",
    "successor_strategist",
    "customer_records_officer",
    "external_auditor",
)


def auth_actor_from_claims(claims: dict[str, object]) -> AuthActor:
    """Pick the effective V1 role and tenant (``tid``) from a verified access token."""
    raw = claims.get("roles")
    if not isinstance(raw, list) or not all(isinstance(x, str) for x in raw):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid roles claim in access token",
        )
    rset = set(raw)
    role: V1Role | None = None
    for candidate in _V1_ORDER:
        if candidate in rset:
            role = candidate
            break
    if role is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No recognized V1 role in access token for this action",
        )
    tid_raw = claims.get("tid")
    tid: str | None
    if isinstance(tid_raw, str) and tid_raw:
        tid = tid_raw
    else:
        tid = None
    return AuthActor(role=role, tenant_id=tid)


def bearer_auth_actor(
    claims: Annotated[dict[str, object], Depends(bearer_access_claims)],
) -> AuthActor:
    """FastAPI dependency: verified bearer token → :class:`AuthActor`."""
    return auth_actor_from_claims(claims)
