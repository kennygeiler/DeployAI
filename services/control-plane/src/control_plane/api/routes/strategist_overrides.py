"""Epic 10 — strategist overrides, private notes, personal audit (internal API)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import get_engine
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.learnings import SolidifiedLearning
from control_plane.domain.canonical_memory.override_payload import OVERRIDE_EVENT_TYPE, parse_override_payload
from control_plane.domain.strategist_personal import PrivateOverrideAnnotation, StrategistActivityEvent
from control_plane.services.learning_override import LearningOverrideError, record_learning_override
from control_plane.services.private_override_crypto import open_private_annotation_ciphertext
from control_plane.services.strategist_activity import append_strategist_activity

router = APIRouter(prefix="/strategist", tags=["internal-strategist-overrides"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class OverrideSubmitBody(BaseModel):
    learning_id: uuid.UUID
    what_changed: str = Field(min_length=1)
    why: str = Field(min_length=20)
    evidence_event_ids: list[uuid.UUID] = Field(min_length=1)
    private_annotation: str | None = Field(default=None, max_length=8000)


class OverrideSubmitResponse(BaseModel):
    override_event_id: uuid.UUID
    learning_id: uuid.UUID
    affected_surfaces: list[str]


_DEFAULT_SURFACES = (
    "Morning Digest",
    "In-Meeting alert",
    "Evening Synthesis",
    "Phase & task tracking",
)


def _actor_uuid(
    x_deployai_actor_id: str | None = Header(default=None, alias="X-DeployAI-Actor-Id"),
) -> uuid.UUID:
    if not x_deployai_actor_id or not x_deployai_actor_id.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-DeployAI-Actor-Id required")
    try:
        return uuid.UUID(x_deployai_actor_id.strip())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-DeployAI-Actor-Id must be a UUID",
        ) from e


def _optional_actor_uuid(
    x_deployai_actor_id: str | None = Header(default=None, alias="X-DeployAI-Actor-Id"),
) -> uuid.UUID | None:
    if not x_deployai_actor_id or not x_deployai_actor_id.strip():
        return None
    try:
        return uuid.UUID(x_deployai_actor_id.strip())
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-DeployAI-Actor-Id must be a UUID",
        ) from e


@router.post(
    "/overrides",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
    response_model=OverrideSubmitResponse,
)
async def post_override(
    body: OverrideSubmitBody,
    tenant_id: Annotated[uuid.UUID, Query(description="Tenant scope")],
    actor_id: Annotated[uuid.UUID, Depends(_actor_uuid)],
) -> OverrideSubmitResponse:
    eng = get_engine()
    async with AsyncSession(eng, expire_on_commit=False) as session:
        try:
            oid = await record_learning_override(
                session,
                tenant_id=tenant_id,
                user_id=actor_id,
                learning_id=body.learning_id,
                override_evidence_event_ids=list(body.evidence_event_ids),
                what_changed=body.what_changed,
                why=body.why,
                private_annotation_plaintext=body.private_annotation,
            )
        except LearningOverrideError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return OverrideSubmitResponse(
        override_event_id=oid,
        learning_id=body.learning_id,
        affected_surfaces=list(_DEFAULT_SURFACES),
    )


class OverrideListRow(BaseModel):
    model_config = ConfigDict(from_attributes=False)

    override_event_id: uuid.UUID
    occurred_at: datetime
    learning_id: uuid.UUID
    learning_belief: str
    reason: str
    overriding_evidence_count: int
    overriding_evidence_event_ids: list[uuid.UUID]
    author_actor_id: uuid.UUID


@router.get(
    "/overrides",
    dependencies=[Depends(require_internal)],
)
async def list_overrides(
    tenant_id: Annotated[uuid.UUID, Query()],
    actor_id: Annotated[uuid.UUID | None, Depends(_optional_actor_uuid)],
    mine_only: Annotated[bool, Query()] = False,
    from_ts: Annotated[datetime | None, Query(alias="from")] = None,
    to_ts: Annotated[datetime | None, Query(alias="to")] = None,
) -> dict[str, Any]:
    if mine_only and actor_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="X-DeployAI-Actor-Id required when mine_only=true",
        )
    eng = get_engine()
    stmt: Select[tuple[CanonicalMemoryEvent]] = select(CanonicalMemoryEvent).where(
        CanonicalMemoryEvent.tenant_id == tenant_id,
        CanonicalMemoryEvent.event_type == OVERRIDE_EVENT_TYPE,
    )
    if from_ts is not None:
        stmt = stmt.where(CanonicalMemoryEvent.created_at >= from_ts)
    if to_ts is not None:
        stmt = stmt.where(CanonicalMemoryEvent.created_at <= to_ts)
    stmt = stmt.order_by(CanonicalMemoryEvent.created_at.desc())

    async with AsyncSession(eng, expire_on_commit=False) as session:
        rows = (await session.execute(stmt)).scalars().all()
        out: list[OverrideListRow] = []
        for ev in rows:
            try:
                payload = parse_override_payload(ev.payload)
            except (TypeError, ValueError):
                continue
            if mine_only and actor_id is not None and payload.user_id != actor_id:
                continue
            belief = ""
            lr = await session.get(SolidifiedLearning, payload.learning_id)
            if lr is not None and lr.tenant_id == tenant_id:
                belief = lr.belief
            out.append(
                OverrideListRow(
                    override_event_id=payload.override_id,
                    occurred_at=ev.occurred_at,
                    learning_id=payload.learning_id,
                    learning_belief=belief,
                    reason=payload.reason_string,
                    overriding_evidence_count=len(payload.override_evidence_event_ids),
                    overriding_evidence_event_ids=list(payload.override_evidence_event_ids),
                    author_actor_id=payload.user_id,
                )
            )
    return {"items": [r.model_dump(mode="json") for r in out]}


@router.get(
    "/overrides/{override_event_id}/private-note",
    dependencies=[Depends(require_internal)],
)
async def read_private_override_note(
    override_event_id: uuid.UUID,
    tenant_id: Annotated[uuid.UUID, Query()],
    actor_id: Annotated[uuid.UUID, Depends(_actor_uuid)],
    x_deployai_effective_role: str | None = Header(default=None, alias="X-DeployAI-Effective-Role"),
    x_deployai_break_glass: str | None = Header(default=None, alias="X-DeployAI-Break-Glass"),
) -> dict[str, str]:
    role = (x_deployai_effective_role or "").strip().lower()
    break_glass = (x_deployai_break_glass or "").strip() == "1"
    eng = get_engine()
    async with AsyncSession(eng, expire_on_commit=False) as session:
        r = await session.execute(
            select(PrivateOverrideAnnotation).where(
                PrivateOverrideAnnotation.tenant_id == tenant_id,
                PrivateOverrideAnnotation.override_event_id == override_event_id,
            )
        )
        row = r.scalar_one_or_none()
        if row is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Private note not found")
        is_author = row.author_actor_id == actor_id
        platform_bg = break_glass and role == "platform_admin"
        if is_author or platform_bg:
            pass
        elif role == "successor_strategist":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Successor cannot read another strategist's private note",
            )
        else:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not the note author")
        decrypted = open_private_annotation_ciphertext(
            tenant_id=tenant_id,
            nonce=row.nonce,
            ciphertext=row.ciphertext,
            wrapped_dek=row.wrapped_dek,
        )
    return {"plaintext": decrypted}


class ActivityEventCreate(BaseModel):
    tenant_id: uuid.UUID
    actor_id: uuid.UUID
    category: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=500)
    detail: dict[str, Any] = Field(default_factory=dict)
    ref_id: uuid.UUID | None = None


@router.post(
    "/activity-events",
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def post_activity_event(body: ActivityEventCreate) -> dict[str, str]:
    eng = get_engine()
    async with AsyncSession(eng, expire_on_commit=False) as session:
        rid = await append_strategist_activity(
            session,
            tenant_id=body.tenant_id,
            actor_id=body.actor_id,
            category=body.category,
            summary=body.summary,
            detail=body.detail,
            ref_id=body.ref_id,
        )
        await session.commit()
    return {"id": str(rid)}


class PersonalAuditRow(BaseModel):
    id: uuid.UUID
    category: str
    summary: str
    detail: dict[str, Any]
    ref_id: uuid.UUID | None
    created_at: datetime


@router.get(
    "/personal-audit",
    dependencies=[Depends(require_internal)],
)
async def get_personal_audit(
    tenant_id: Annotated[uuid.UUID, Query()],
    actor_id: Annotated[uuid.UUID, Depends(_actor_uuid)],
    category: Annotated[str | None, Query()] = None,
) -> dict[str, Any]:
    eng = get_engine()
    stmt = select(StrategistActivityEvent).where(
        StrategistActivityEvent.tenant_id == tenant_id,
        StrategistActivityEvent.actor_id == actor_id,
    )
    if category:
        stmt = stmt.where(StrategistActivityEvent.category == category)
    stmt = stmt.order_by(StrategistActivityEvent.created_at.desc())
    async with AsyncSession(eng, expire_on_commit=False) as session:
        rows = (await session.execute(stmt)).scalars().all()
        items = [
            PersonalAuditRow(
                id=r.id,
                category=r.category,
                summary=r.summary,
                detail=r.detail,
                ref_id=r.ref_id,
                created_at=r.created_at,
            )
            for r in rows
        ]
    return {"items": [i.model_dump(mode="json") for i in items]}
