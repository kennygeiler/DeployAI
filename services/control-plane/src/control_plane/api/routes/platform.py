"""Platform admin routes (Story 2-5: account provisioning)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from control_plane.api.routes.auth import require_platform_admin
from control_plane.db import AppDbSession
from control_plane.exceptions import AccountProvisionError, TenantDekModeNotAvailableError
from control_plane.schemas.platform import PlatformAccountCreate, PlatformAccountCreated
from control_plane.services.account_provision import provision_platform_account

logger = logging.getLogger(__name__)

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
    try:
        return await provision_platform_account(
            session,
            organization_name=body.organization_name,
            initial_strategist_email=str(body.initial_strategist_email),
            actor_sub=sub if isinstance(sub, str) else None,
        )
    except TenantDekModeNotAvailableError as e:
        logger.warning("account.provision.tenant_dek_unavailable: %s", e)
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Requested tenant encryption mode is not available in this deployment",
        ) from None
    except AccountProvisionError:
        logger.exception("account.provision.failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Account provisioning could not be completed",
        ) from None
