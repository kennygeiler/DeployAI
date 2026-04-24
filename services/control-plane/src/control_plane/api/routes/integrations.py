"""Integration kill-switch (Epic 2 Story 2-6) — plumb to Epic 3 providers + SQS + secrets later."""

from __future__ import annotations

import uuid
from typing import Annotated

from deployai_authz import AuthActor, can_access
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from control_plane.api.jwt_actor import bearer_auth_actor
from control_plane.db import AppDbSession
from control_plane.domain.integrations.models import Integration
from control_plane.services.integration_kill_switch import disable_integration

router = APIRouter(prefix="/integrations", tags=["integrations"])


@router.post(
    "/{integration_id}/disable",
    status_code=status.HTTP_200_OK,
)
async def post_integration_disable(
    integration_id: uuid.UUID,
    session: AppDbSession,
    actor: Annotated[AuthActor, Depends(bearer_auth_actor)],
) -> dict[str, object]:
    r = await session.execute(select(Integration).where(Integration.id == integration_id).limit(1))
    it = r.scalar_one_or_none()
    if it is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    d = can_access(
        actor,
        "integration:kill_switch",
        {"kind": "tenant", "id": str(it.tenant_id)},
        skip_audit=False,
    )
    if not d.allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=d.reason)
    out = await disable_integration(session, integration_id)
    if out.get("not_found") is True:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Integration not found")
    return {k: v for k, v in out.items() if k != "not_found"}
