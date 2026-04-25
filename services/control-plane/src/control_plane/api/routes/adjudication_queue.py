"""Internal adjudication queue listing + create (Epic 4 Story 4-7) for ``/admin/adjudication``.

``meta`` (JSONB) is opaque: producers may store eval flags, notes, and optional
``citation_envelope`` (+ ``evidence_body``, etc.) for the web Memory column. See
``docs/platform/adjudication-queue-meta.md``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import get_app_db_session
from control_plane.domain.adjudication import AdjudicationQueueItem
from control_plane.domain.app_identity.models import AppTenant

# OpenAPI: consumers read `citation_envelope` + web keys in ``docs/platform/adjudication-queue-meta.md``.
_ADJD_QUEUE_META_DOCS = (
    "Arbitrary JSON (JSONB). "
    "Optional `citation_envelope` (v0.1.0) and `evidence_body` for web — see "
    "docs/platform/adjudication-queue-meta.md."
)

router = APIRouter(
    prefix="/adjudication-queue-items",
    tags=["internal-adjudication-queue"],
)


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class AdjudicationItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    tenant_id: uuid.UUID
    query_id: str
    status: str
    meta: dict[str, Any] = Field(default_factory=dict, description=_ADJD_QUEUE_META_DOCS)
    created_at: datetime
    updated_at: datetime


class AdjudicationItemCreate(BaseModel):
    tenant_id: uuid.UUID
    query_id: str
    status: str = "open"
    meta: dict[str, Any] = Field(default_factory=dict, description=_ADJD_QUEUE_META_DOCS)


class AdjudicationItemPatch(BaseModel):
    status: str | None = None
    meta: dict[str, Any] | None = Field(default=None, description=_ADJD_QUEUE_META_DOCS)


@router.get(
    "",
    response_model=list[AdjudicationItemRead],
    dependencies=[Depends(require_internal)],
)
async def list_adjudication_items(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    limit: int = Query(100, le=500, ge=1),
) -> list[AdjudicationItemRead]:
    r = await session.execute(
        select(AdjudicationQueueItem).order_by(desc(AdjudicationQueueItem.created_at)).limit(int(limit))
    )
    rows = r.scalars().all()
    return [AdjudicationItemRead.model_validate(x) for x in rows]


@router.post(
    "",
    response_model=AdjudicationItemRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_adjudication_item(
    body: AdjudicationItemCreate,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> AdjudicationQueueItem:
    """Create a queue item; ``body.meta`` may include ``citation_envelope`` (see module doc + docs)."""
    t = await session.get(AppTenant, body.tenant_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    row = AdjudicationQueueItem(
        tenant_id=body.tenant_id,
        query_id=body.query_id,
        status=body.status,
        meta=body.meta,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


@router.patch(
    "/{item_id}",
    response_model=AdjudicationItemRead,
    dependencies=[Depends(require_internal)],
)
async def patch_adjudication_item(
    item_id: uuid.UUID,
    body: AdjudicationItemPatch,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
) -> AdjudicationQueueItem:
    r = await session.get(AdjudicationQueueItem, item_id)
    if r is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="item not found")
    if body.status is not None:
        r.status = body.status
    if body.meta is not None:
        r.meta = body.meta
    if body.status is not None or body.meta is not None:
        r.updated_at = datetime.now(tz=UTC)
        await session.commit()
        await session.refresh(r)
    return r
