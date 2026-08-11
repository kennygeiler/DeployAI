"""Internal API — per-tenant service tokens (pilot-refresh A4).

Mint, list, and revoke ``internal_service_tokens`` rows. These endpoints are
the bootstrap path for migrating internal callers off the global
``X-DeployAI-Internal-Key``, so they are gated by :func:`require_internal`
(the global key itself) rather than :func:`require_tenant_scoped` — a tenant
token must not be able to mint further tokens.

The raw token is returned exactly once at mint time; subsequent reads expose
only the row id, name, and lifecycle timestamps (the secret stays hashed in
Postgres). Same contract as ``tenant_api_keys_internal.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_auth import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.app_identity.service_tokens import (
    InternalServiceToken,
    generate_raw_token,
    hash_service_token,
)

router = APIRouter(prefix="/tenant/service-tokens", tags=["internal-service-tokens"])

_MAX_NAME_CHARS = 120


class ServiceTokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    created_at: datetime
    revoked_at: datetime | None


class ServiceTokenMintRequest(BaseModel):
    name: str = Field(min_length=1, max_length=_MAX_NAME_CHARS)


class ServiceTokenMintResponse(BaseModel):
    service_token: ServiceTokenRead
    raw_token: str


class ServiceTokenListResponse(BaseModel):
    service_tokens: list[ServiceTokenRead]


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> AppTenant:
    tenant = await session.get(AppTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return tenant


@router.get("", response_model=ServiceTokenListResponse, dependencies=[Depends(require_internal)])
async def list_service_tokens(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ServiceTokenListResponse:
    await _require_tenant(session, tenant_id)
    stmt = (
        select(InternalServiceToken)
        .where(InternalServiceToken.tenant_id == tenant_id)
        .order_by(InternalServiceToken.created_at.desc())
    )
    rows = list((await session.execute(stmt)).scalars().all())
    return ServiceTokenListResponse(service_tokens=[ServiceTokenRead.model_validate(r) for r in rows])


@router.post(
    "",
    response_model=ServiceTokenMintResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def mint_service_token(
    body: ServiceTokenMintRequest,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ServiceTokenMintResponse:
    await _require_tenant(session, tenant_id)

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name must be non-empty")

    existing = (
        await session.execute(
            select(InternalServiceToken).where(
                InternalServiceToken.tenant_id == tenant_id,
                InternalServiceToken.name == name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="a service token with this name already exists for the tenant",
        )

    raw_token = generate_raw_token()
    row = InternalServiceToken(
        tenant_id=tenant_id,
        name=name,
        hashed_key=hash_service_token(raw_token),
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return ServiceTokenMintResponse(
        service_token=ServiceTokenRead.model_validate(row),
        raw_token=raw_token,
    )


@router.delete(
    "/{token_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def revoke_service_token(
    token_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> None:
    await _require_tenant(session, tenant_id)
    row = (
        await session.execute(
            select(InternalServiceToken).where(
                InternalServiceToken.tenant_id == tenant_id,
                InternalServiceToken.id == token_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="service token not found")
    if row.revoked_at is None:
        row.revoked_at = datetime.now(UTC)
    await session.commit()
