"""Internal test-only session mint (Story 2-4) — still requires X-DeployAI-Internal-Key."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

from control_plane.auth.session_service import issue_tokens
from control_plane.config.internal_api import verify_internal_key
from control_plane.config.settings import get_settings

router = APIRouter(prefix="/test", tags=["internal-session"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class MintSessionBody(BaseModel):
    tenant_id: uuid.UUID
    user_id: uuid.UUID
    roles: list[str] = Field(..., min_length=1, description="Non-empty; stored for refresh rotation")


@router.post("/session-tokens", dependencies=[Depends(require_internal)], status_code=status.HTTP_201_CREATED)
async def mint_test_session(body: MintSessionBody) -> dict[str, object]:
    if not get_settings().allow_test_session_mint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Test session mint disabled (set DEPLOYAI_ALLOW_TEST_SESSION_MINT=1 for dev/tests)",
        )
    pair = await issue_tokens(body.tenant_id, body.user_id, body.roles)
    return {
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_jti,
        "token_type": pair.token_type,
        "expires_in": pair.expires_in,
    }
