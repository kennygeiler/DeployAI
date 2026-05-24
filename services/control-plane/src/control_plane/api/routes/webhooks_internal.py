"""Internal API — per-tenant webhook subscriptions (Sprint 8).

Mounted under ``/internal/v1``. Tenants register HTTPS endpoints that
receive signed POST payloads for specific tenant events. Secret is
auto-generated on POST if not supplied and surfaced once in the
response; subsequent GETs mask it.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime
from typing import Annotated, Any
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.webhooks.models import TenantWebhook, WebhookDelivery
from control_plane.webhooks.dispatcher import WEBHOOK_EVENTS

router = APIRouter(prefix="/webhooks", tags=["internal-webhooks"])


def _mask_secret(value: str | None) -> str | None:
    if not value:
        return None
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}{'*' * (len(value) - 8)}{value[-4:]}"


def _validate_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme == "https":
        return
    if parsed.scheme == "http" and parsed.hostname and parsed.hostname.startswith("localhost"):
        return
    raise HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail="url must be https or http://localhost*",
    )


def _validate_events(events: list[str]) -> None:
    invalid = [e for e in events if e not in WEBHOOK_EVENTS]
    if invalid:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid events: {invalid}",
        )


async def _require_tenant(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    if await session.get(AppTenant, tenant_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")


class WebhookCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=1, max_length=2000)
    events: list[str] = Field(default_factory=list)
    secret: str | None = Field(default=None, max_length=500)
    active: bool = True


class WebhookUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    url: str | None = Field(default=None, min_length=1, max_length=2000)
    events: list[str] | None = None
    active: bool | None = None


class WebhookRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    url: str
    events: list[str]
    active: bool
    secret_masked: str | None
    has_secret: bool
    created_at: datetime
    updated_at: datetime


class WebhookCreateResponse(WebhookRead):
    """Response from POST — includes the plaintext secret one time."""

    secret: str | None = None


class WebhookDeliveryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    webhook_id: uuid.UUID
    event_name: str
    payload: dict[str, Any]
    status: str
    response_status: int | None
    error: str | None
    attempts: int
    created_at: datetime
    completed_at: datetime | None


def _to_read(row: TenantWebhook) -> WebhookRead:
    return WebhookRead(
        id=row.id,
        tenant_id=row.tenant_id,
        name=row.name,
        url=row.url,
        events=list(row.events or []),
        active=row.active,
        secret_masked=_mask_secret(row.secret_ciphertext),
        has_secret=bool(row.secret_ciphertext),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("", response_model=list[WebhookRead], dependencies=[Depends(require_internal)])
async def list_webhooks(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[WebhookRead]:
    await _require_tenant(session, tenant_id)
    r = await session.execute(
        select(TenantWebhook).where(TenantWebhook.tenant_id == tenant_id).order_by(TenantWebhook.created_at.desc())
    )
    return [_to_read(row) for row in r.scalars().all()]


@router.post(
    "",
    response_model=WebhookCreateResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_webhook(
    body: WebhookCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> WebhookCreateResponse:
    await _require_tenant(session, tenant_id)
    _validate_url(body.url)
    _validate_events(body.events)
    secret = body.secret or secrets.token_urlsafe(32)
    row = TenantWebhook(
        tenant_id=tenant_id,
        name=body.name,
        url=body.url,
        secret_ciphertext=secret,
        events=body.events,
        active=body.active,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    read = _to_read(row)
    return WebhookCreateResponse(**read.model_dump(), secret=secret)


@router.get(
    "/{webhook_id}",
    response_model=WebhookRead,
    dependencies=[Depends(require_internal)],
)
async def get_webhook(
    webhook_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> WebhookRead:
    await _require_tenant(session, tenant_id)
    r = await session.execute(
        select(TenantWebhook).where(
            TenantWebhook.tenant_id == tenant_id,
            TenantWebhook.id == webhook_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook not found")
    return _to_read(row)


@router.put(
    "/{webhook_id}",
    response_model=WebhookRead,
    dependencies=[Depends(require_internal)],
)
async def update_webhook(
    webhook_id: uuid.UUID,
    body: WebhookUpdate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> WebhookRead:
    await _require_tenant(session, tenant_id)
    r = await session.execute(
        select(TenantWebhook).where(
            TenantWebhook.tenant_id == tenant_id,
            TenantWebhook.id == webhook_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook not found")
    if body.url is not None:
        _validate_url(body.url)
        row.url = body.url
    if body.events is not None:
        _validate_events(body.events)
        row.events = body.events
    if body.name is not None:
        row.name = body.name
    if body.active is not None:
        row.active = body.active
    await session.commit()
    await session.refresh(row)
    return _to_read(row)


@router.delete(
    "/{webhook_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def delete_webhook(
    webhook_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> None:
    await _require_tenant(session, tenant_id)
    r = await session.execute(
        select(TenantWebhook).where(
            TenantWebhook.tenant_id == tenant_id,
            TenantWebhook.id == webhook_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook not found")
    await session.delete(row)
    await session.commit()


@router.get(
    "/{webhook_id}/deliveries",
    response_model=list[WebhookDeliveryRead],
    dependencies=[Depends(require_internal)],
)
async def list_deliveries(
    webhook_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> list[WebhookDelivery]:
    await _require_tenant(session, tenant_id)
    wh = await session.execute(
        select(TenantWebhook.id).where(
            TenantWebhook.tenant_id == tenant_id,
            TenantWebhook.id == webhook_id,
        )
    )
    if wh.scalar_one_or_none() is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="webhook not found")
    r = await session.execute(
        select(WebhookDelivery)
        .where(WebhookDelivery.webhook_id == webhook_id)
        .order_by(WebhookDelivery.created_at.desc())
        .limit(limit)
    )
    return list(r.scalars().all())
