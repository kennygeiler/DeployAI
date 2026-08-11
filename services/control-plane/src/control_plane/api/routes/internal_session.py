"""Internal test-only session mint (Story 2-4) — still requires X-DeployAI-Internal-Key."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from control_plane.auth.session_service import issue_tokens
from control_plane.config.internal_auth import require_internal
from control_plane.config.settings import get_settings

router = APIRouter(prefix="/test", tags=["internal-session"])


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
