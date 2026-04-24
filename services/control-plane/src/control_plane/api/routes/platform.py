"""Platform admin routes (Story 2-5: account provisioning)."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from control_plane.api.routes.auth import require_platform_admin
from control_plane.db import AppDbSession
from control_plane.schemas.platform import PlatformAccountCreate, PlatformAccountCreated
from control_plane.services.account_provision import provision_platform_account

router = APIRouter(prefix="/platform", tags=["platform"])


@router.post(
    "/accounts",
    status_code=status.HTTP_201_CREATED,
    response_model=PlatformAccountCreated,
)
async def create_account(
    body: PlatformAccountCreate,
    session: AppDbSession,
    claims: Annotated[dict[str, object], Depends(require_platform_admin)],
) -> PlatformAccountCreated:
    sub = claims.get("sub")
    return await provision_platform_account(
        session,
        organization_name=body.organization_name,
        initial_strategist_email=str(body.initial_strategist_email),
        actor_sub=sub if isinstance(sub, str) else None,
    )
