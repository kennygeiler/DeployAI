"""Internal API — durable strategist queues (action / validation / solidification).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``; callers must pass ``tenant_id`` query scope.

"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import get_app_db_session
from control_plane.domain.app_identity.models import AppTenant
from control_plane.domain.strategist_queues import (
    StrategistActionQueueItem,
    StrategistSolidificationQueueItem,
    StrategistValidationQueueItem,
)

router = APIRouter(prefix="/strategist", tags=["internal-strategist-queues"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


def _validation_seed_rows(tenant_id: uuid.UUID) -> list[StrategistValidationQueueItem]:
    out: list[StrategistValidationQueueItem] = []
    now = datetime.now(tz=UTC)
    for i in range(10):
        out.append(
            StrategistValidationQueueItem(
                id=f"vq-{i + 1}",
                tenant_id=tenant_id,
                proposed_fact=(f"Validation candidate {i + 1}: low-confidence extraction pending strategist review."),
                confidence=f"{0.55 + i * 0.03:.2f}",
                state="unresolved",
                created_at=now,
                updated_at=now,
            )
        )
    return out


def _solidification_seed_rows(tenant_id: uuid.UUID) -> list[StrategistSolidificationQueueItem]:
    out: list[StrategistSolidificationQueueItem] = []
    now = datetime.now(tz=UTC)
    for i in range(20):
        out.append(
            StrategistSolidificationQueueItem(
                id=f"sq-{i + 1}",
                tenant_id=tenant_id,
                proposed_fact=f"Class B candidate {i + 1}: weekly solidification review item (mock).",
                confidence="Class B",
                state="unresolved",
                created_at=now,
                updated_at=now,
            )
        )
    return out


async def _ensure_validation_solidification_seed(
    session: AsyncSession,
    tenant_id: uuid.UUID,
) -> None:
    """Mirror ``seedStrategistQueuesIfEmpty`` from ``strategist-queues-store.ts``."""
    rv = await session.execute(
        select(func.count())
        .select_from(StrategistValidationQueueItem)
        .where(
            StrategistValidationQueueItem.tenant_id == tenant_id,
        )
    )
    if (rv.scalar_one() or 0) == 0:
        for validation_row in _validation_seed_rows(tenant_id):
            session.add(validation_row)
    rs = await session.execute(
        select(func.count())
        .select_from(StrategistSolidificationQueueItem)
        .where(
            StrategistSolidificationQueueItem.tenant_id == tenant_id,
        )
    )
    if (rs.scalar_one() or 0) == 0:
        for solid_row in _solidification_seed_rows(tenant_id):
            session.add(solid_row)
    await session.commit()


# --- Action queue ---


class ActionQueueItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: str
    priority: str
    phase: str
    description: str
    status: str
    claimed_by: str | None
    updated_at: str
    source: str | None = None
    evidence_node_ids: list[str] = Field(default_factory=list)
    resolution_reason: str | None = None
    evidence_event_ids: list[str] | None = None


def _action_read(row: StrategistActionQueueItem) -> ActionQueueItemRead:
    ev_ids: list[str] | None = None
    raw_ev = row.evidence_event_ids
    if isinstance(raw_ev, list):
        ev_ids = [str(x) for x in raw_ev]
    return ActionQueueItemRead(
        id=row.id,
        priority=row.priority,
        phase=row.phase,
        description=row.description,
        status=row.status,
        claimed_by=row.claimed_by,
        updated_at=row.updated_at.isoformat(),
        source=row.source,
        evidence_node_ids=list(row.evidence_node_ids or []),
        resolution_reason=row.resolution_reason,
        evidence_event_ids=ev_ids,
    )


def _parse_updated_at_iso(iso: str | None, fallback: datetime) -> datetime:
    if not iso:
        return fallback
    s = iso.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return fallback


class ActionQueueBulkRow(BaseModel):
    id: str
    priority: str
    phase: str
    description: str
    status: str = "open"
    claimed_by: str | None = None
    updated_at: str | None = None
    source: str | None = None
    evidence_node_ids: list[str] = Field(default_factory=list)


class ActionQueueBulkBody(BaseModel):
    items: list[ActionQueueBulkRow]


class ActionQueuePatchBody(BaseModel):
    status: str
    claimed_by: str | None = None
    resolution_reason: str | None = None
    evidence_event_ids: list[str] | None = None


@router.get(
    "/action-queue-items",
    response_model=list[ActionQueueItemRead],
    dependencies=[Depends(require_internal)],
)
async def list_action_queue_items(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[ActionQueueItemRead]:
    t = await session.get(AppTenant, tenant_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    r = await session.execute(
        select(StrategistActionQueueItem)
        .where(StrategistActionQueueItem.tenant_id == tenant_id)
        .order_by(StrategistActionQueueItem.updated_at.desc())
    )
    rows = r.scalars().all()
    return [_action_read(x) for x in rows]


@router.post(
    "/action-queue-items/bulk",
    response_model=list[ActionQueueItemRead],
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def bulk_append_action_queue_items(
    body: ActionQueueBulkBody,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> list[ActionQueueItemRead]:
    t = await session.get(AppTenant, tenant_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    out: list[StrategistActionQueueItem] = []
    now = datetime.now(tz=UTC)
    for it in body.items:
        row = StrategistActionQueueItem(
            id=it.id,
            tenant_id=tenant_id,
            priority=it.priority,
            phase=it.phase,
            description=it.description,
            status=it.status,
            claimed_by=it.claimed_by,
            updated_at=_parse_updated_at_iso(it.updated_at, now),
            source=it.source,
            evidence_node_ids=it.evidence_node_ids,
            resolution_reason=None,
            evidence_event_ids=None,
        )
        session.add(row)
        out.append(row)
    await session.commit()
    for row in out:
        await session.refresh(row)
    return [_action_read(x) for x in out]


@router.patch(
    "/action-queue-items/{item_id}",
    response_model=ActionQueueItemRead,
    dependencies=[Depends(require_internal)],
)
async def patch_action_queue_item(
    item_id: str,
    body: ActionQueuePatchBody,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ActionQueueItemRead:
    r = await session.execute(
        select(StrategistActionQueueItem).where(
            StrategistActionQueueItem.tenant_id == tenant_id,
            StrategistActionQueueItem.id == item_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    terminal = {"resolved", "deferred", "rejected_with_reason"}
    row.status = body.status
    if body.claimed_by is not None:
        row.claimed_by = body.claimed_by
    row.updated_at = datetime.now(tz=UTC)
    if body.status in terminal:
        row.resolution_reason = body.resolution_reason
        row.evidence_event_ids = body.evidence_event_ids
    await session.commit()
    await session.refresh(row)
    return _action_read(row)


# --- Validation queue ---


class ValidationQueueItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: str
    proposed_fact: str
    confidence: str
    state: str


@router.get(
    "/validation-queue-items",
    response_model=list[ValidationQueueItemRead],
    dependencies=[Depends(require_internal)],
)
async def list_validation_queue_items(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    seed_if_empty: Annotated[bool, Query()] = True,
) -> list[ValidationQueueItemRead]:
    t = await session.get(AppTenant, tenant_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    if seed_if_empty:
        await _ensure_validation_solidification_seed(session, tenant_id)
    r = await session.execute(
        select(StrategistValidationQueueItem).where(StrategistValidationQueueItem.tenant_id == tenant_id)
    )
    rows = r.scalars().all()
    active = [x for x in rows if x.state in ("unresolved", "in-review")]
    return [
        ValidationQueueItemRead(id=x.id, proposed_fact=x.proposed_fact, confidence=x.confidence, state=x.state)
        for x in active
    ]


class ValidationPatchBody(BaseModel):
    state: str


@router.patch(
    "/validation-queue-items/{item_id}",
    response_model=ValidationQueueItemRead,
    dependencies=[Depends(require_internal)],
)
async def patch_validation_queue_item(
    item_id: str,
    body: ValidationPatchBody,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> ValidationQueueItemRead:
    r = await session.execute(
        select(StrategistValidationQueueItem).where(
            StrategistValidationQueueItem.tenant_id == tenant_id,
            StrategistValidationQueueItem.id == item_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    row.state = body.state
    row.updated_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(row)
    return ValidationQueueItemRead(
        id=row.id,
        proposed_fact=row.proposed_fact,
        confidence=row.confidence,
        state=row.state,
    )


# --- Solidification queue ---


class SolidificationQueueItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    id: str
    proposed_fact: str
    confidence: str
    state: str


@router.get(
    "/solidification-queue-items",
    response_model=list[SolidificationQueueItemRead],
    dependencies=[Depends(require_internal)],
)
async def list_solidification_queue_items(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
    seed_if_empty: Annotated[bool, Query()] = True,
) -> list[SolidificationQueueItemRead]:
    t = await session.get(AppTenant, tenant_id)
    if t is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tenant not found")
    if seed_if_empty:
        await _ensure_validation_solidification_seed(session, tenant_id)
    r = await session.execute(
        select(StrategistSolidificationQueueItem).where(StrategistSolidificationQueueItem.tenant_id == tenant_id)
    )
    rows = r.scalars().all()
    active = [x for x in rows if x.state in ("unresolved", "in-review")]
    return [
        SolidificationQueueItemRead(id=x.id, proposed_fact=x.proposed_fact, confidence=x.confidence, state=x.state)
        for x in active
    ]


class SolidificationPatchBody(BaseModel):
    state: str


@router.patch(
    "/solidification-queue-items/{item_id}",
    response_model=SolidificationQueueItemRead,
    dependencies=[Depends(require_internal)],
)
async def patch_solidification_queue_item(
    item_id: str,
    body: SolidificationPatchBody,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> SolidificationQueueItemRead:
    r = await session.execute(
        select(StrategistSolidificationQueueItem).where(
            StrategistSolidificationQueueItem.tenant_id == tenant_id,
            StrategistSolidificationQueueItem.id == item_id,
        )
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="not found")
    row.state = body.state
    row.updated_at = datetime.now(tz=UTC)
    await session.commit()
    await session.refresh(row)
    return SolidificationQueueItemRead(
        id=row.id,
        proposed_fact=row.proposed_fact,
        confidence=row.confidence,
        state=row.state,
    )
