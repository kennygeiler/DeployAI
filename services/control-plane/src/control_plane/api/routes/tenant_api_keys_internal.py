"""Internal API — tenant API keys for the MCP inbound server (v2 Phase 4).

The web BFF posts here to mint, list, and revoke ``tenant_api_keys`` rows.
Raw keys are returned exactly once at mint time; subsequent reads expose only
the row id, name, scopes, and lifecycle timestamps (the secret stays hashed
in Postgres). See scope-v2 §8.4.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.api_keys import (
    TenantApiKey,
    generate_raw_key,
    hash_raw_key,
)
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.engagement import Engagement
from control_plane.ledger import emit_ledger_event

router = APIRouter(prefix="/tenant/api-keys", tags=["internal-tenant-api-keys"])

_MAX_NAME_CHARS = 120
_ALLOWED_SCOPES: frozenset[str] = frozenset({"read"})


class ApiKeyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    engagement_id: uuid.UUID | None
    name: str
    scopes: list[str]
    last_used_at: datetime | None
    created_at: datetime
    revoked_at: datetime | None


class ApiKeyMintRequest(BaseModel):
    name: str = Field(min_length=1, max_length=_MAX_NAME_CHARS)
    engagement_id: uuid.UUID
    scopes: list[str] | None = None


class ApiKeyMintResponse(BaseModel):
    api_key: ApiKeyRead
    raw_key: str


class ApiKeyListResponse(BaseModel):
    api_keys: list[ApiKeyRead]


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> AppTenant:
    tenant = await session.get(AppTenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    return tenant


async def _require_engagement(session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> Engagement:
    eng = await session.get(Engagement, engagement_id)
    if eng is None or eng.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    return eng


@router.get("", response_model=ApiKeyListResponse, dependencies=[Depends(require_internal)])
async def list_tenant_api_keys(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ApiKeyListResponse:
    await _require_tenant(session, tenant_id)
    stmt = select(TenantApiKey).where(TenantApiKey.tenant_id == tenant_id).order_by(TenantApiKey.created_at.desc())
    rows = list((await session.execute(stmt)).scalars().all())
    return ApiKeyListResponse(api_keys=[ApiKeyRead.model_validate(r) for r in rows])


@router.post(
    "",
    response_model=ApiKeyMintResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def mint_tenant_api_key(
    body: ApiKeyMintRequest,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ApiKeyMintResponse:
    await _require_tenant(session, tenant_id)
    await _require_engagement(session, tenant_id, body.engagement_id)

    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="name must be non-empty")

    scopes = body.scopes or ["read"]
    bad_scopes = [s for s in scopes if s not in _ALLOWED_SCOPES]
    if bad_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported scopes: {bad_scopes}",
        )

    existing = (
        await session.execute(
            select(TenantApiKey).where(
                TenantApiKey.tenant_id == tenant_id,
                TenantApiKey.name == name,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="an api key with this name already exists for the tenant",
        )

    raw_key = generate_raw_key()
    row = TenantApiKey(
        tenant_id=tenant_id,
        engagement_id=body.engagement_id,
        name=name,
        hashed_secret=hash_raw_key(raw_key),
        scopes=scopes,
    )
    session.add(row)
    await session.flush()

    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=body.engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=None,
        source_kind="tenant_api_key_minted",
        source_ref=row.id,
        summary=f"tenant_api_key_minted: {name}",
        detail={
            "api_key_id": str(row.id),
            "name": name,
            "engagement_id": str(body.engagement_id),
            "scopes": list(scopes),
        },
    )
    await session.commit()
    await session.refresh(row)
    return ApiKeyMintResponse(api_key=ApiKeyRead.model_validate(row), raw_key=raw_key)


@router.delete(
    "/{api_key_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def revoke_tenant_api_key(
    api_key_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> None:
    await _require_tenant(session, tenant_id)
    row = (
        await session.execute(
            select(TenantApiKey).where(
                TenantApiKey.tenant_id == tenant_id,
                TenantApiKey.id == api_key_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="api key not found")
    if row.revoked_at is not None:
        await session.commit()
        return
    now = datetime.now(UTC)
    row.revoked_at = now
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=row.engagement_id,
        occurred_at=now,
        actor_kind="user",
        actor_id=None,
        source_kind="tenant_api_key_revoked",
        source_ref=row.id,
        summary=f"tenant_api_key_revoked: {row.name}",
        detail={
            "api_key_id": str(row.id),
            "name": row.name,
            "engagement_id": str(row.engagement_id) if row.engagement_id else None,
        },
    )
    await session.commit()
