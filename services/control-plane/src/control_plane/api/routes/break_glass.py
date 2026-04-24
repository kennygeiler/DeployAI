"""Break-glass session API (Epic 2 Story 2-7; UI + customer notification in Epic 12)."""

from __future__ import annotations

import uuid
from typing import Annotated

from deployai_authz import can_access
from fastapi import APIRouter, Depends, HTTPException, Response, status

from control_plane.api.break_glass_http import require_break_glass_webauthn
from control_plane.api.jwt_actor import auth_actor_from_claims
from control_plane.api.routes.auth import require_platform_admin
from control_plane.db import AppDbSession
from control_plane.exceptions import NotFoundError
from control_plane.schemas.break_glass import BreakGlassRequestBody, BreakGlassSessionRead
from control_plane.services.break_glass import approve, create_request, revoke

router = APIRouter(prefix="/break-glass", tags=["break-glass"])


@router.post(
    "/request",
    response_model=BreakGlassSessionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_break_glass_webauthn)],
)
async def break_glass_request(
    body: BreakGlassRequestBody,
    session: AppDbSession,
    claims: Annotated[dict[str, object], Depends(require_platform_admin)],
) -> BreakGlassSessionRead:
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject in token")
    actor = auth_actor_from_claims(claims)
    d = can_access(
        actor,
        "break_glass:invoke",
        {"kind": "tenant", "id": str(body.tenant_id)},
        skip_audit=False,
    )
    if not d.allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=d.reason)
    row = await create_request(
        session,
        tenant_id=body.tenant_id,
        initiator_sub=sub,
        requested_scope=body.requested_scope,
    )
    return BreakGlassSessionRead.model_validate(row, from_attributes=True)


@router.post(
    "/approve/{session_id}",
    response_model=BreakGlassSessionRead,
    dependencies=[Depends(require_break_glass_webauthn)],
)
async def break_glass_approve(
    session_id: uuid.UUID,
    session: AppDbSession,
    claims: Annotated[dict[str, object], Depends(require_platform_admin)],
) -> BreakGlassSessionRead:
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject in token")
    try:
        row = await approve(session, session_id=session_id, approver_sub=sub)
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return BreakGlassSessionRead.model_validate(row, from_attributes=True)


@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_break_glass_webauthn)],
)
async def break_glass_delete(
    session_id: uuid.UUID,
    session: AppDbSession,
    claims: Annotated[dict[str, object], Depends(require_platform_admin)],
) -> Response:
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid subject in token")
    try:
        await revoke(
            session,
            session_id=session_id,
            actor_sub=sub,
            allow_if_platform=True,
        )
    except NotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return Response(status_code=status.HTTP_204_NO_CONTENT)
