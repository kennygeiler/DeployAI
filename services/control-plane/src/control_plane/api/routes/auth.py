"""Auth session API: refresh, logout, admin revoke-all (Story 2-4)."""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from pydantic import BaseModel, Field

from control_plane.auth import session_service as session_service_mod
from control_plane.auth.jwt_tokens import verify_access_token
from control_plane.auth.session_service import (
    InvalidRefreshError,
    TenantMismatchError,
    revoke_all_for_user,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


class RefreshBody(BaseModel):
    tenant_id: uuid.UUID
    refresh_token: str = Field(..., description="Opaque refresh token (JTI) from issue or prior refresh")


class LogoutBody(BaseModel):
    tenant_id: uuid.UUID
    refresh_token: str


def bearer_access_claims(
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    if not authorization or not authorization.strip().lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Authorization: Bearer access token",
        )
    raw = authorization[7:].strip()
    try:
        return verify_access_token(raw)
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from e


def require_platform_admin(
    claims: Annotated[dict[str, object], Depends(bearer_access_claims)],
) -> dict[str, object]:
    roles = claims.get("roles")
    if not isinstance(roles, list) or "platform_admin" not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="platform_admin role required",
        )
    if claims.get("token_use") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not an access token")
    return claims


@router.post("/refresh", status_code=status.HTTP_200_OK)
async def refresh_session(body: RefreshBody) -> dict[str, object]:
    try:
        pair = await session_service_mod.refresh_tokens(body.tenant_id, body.refresh_token)
    except InvalidRefreshError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e
    except TenantMismatchError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch") from e
    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_jti,
        "token_type": pair.token_type,
        "expires_in": pair.expires_in,
    }


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout_session(body: LogoutBody) -> Response:
    ok = await session_service_mod.logout(body.tenant_id, body.refresh_token)
    if not ok:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown refresh token")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sessions/revoke-all/{user_id}", status_code=status.HTTP_200_OK)
async def revoke_all_sessions_for_user(
    user_id: uuid.UUID,
    claims: Annotated[dict[str, object], Depends(require_platform_admin)],
) -> dict[str, object]:
    tid_raw = claims.get("tid")
    if not isinstance(tid_raw, str):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token tenant")
    tenant_id = uuid.UUID(tid_raw)
    n = await revoke_all_for_user(tenant_id, user_id)
    logger.info(
        "audit.sessions.revoke_all",
        extra={
            "tenant_id": str(tenant_id),
            "target_user_id": str(user_id),
            "actor_sub": claims.get("sub"),
            "deleted_refresh_keys": n,
        },
    )
    return {"ok": True, "deleted_refresh_keys": n}
