"""Epic 11.2 — internal edge-agent registration (per-device Ed25519 public key)."""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from control_plane.config.internal_api import verify_internal_key
from control_plane.db import AppDbSession
from control_plane.domain.edge_agents import EdgeAgent

router = APIRouter(prefix="/edge-agents", tags=["internal-edge-agents"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class EdgeAgentRegisterBody(BaseModel):
    tenant_id: uuid.UUID
    device_id: uuid.UUID
    public_key_ed25519_b64: str = Field(min_length=1)


class EdgeAgentRegisterResponse(BaseModel):
    edge_agent_id: uuid.UUID
    registered_at: datetime


class EdgeAgentReadResponse(BaseModel):
    edge_agent_id: uuid.UUID
    tenant_id: uuid.UUID
    device_id: uuid.UUID
    public_key_ed25519_b64: str
    registered_at: datetime
    revoked_at: datetime | None


def _decode_ed25519_public(b64: str) -> bytes:
    raw = b64.strip().encode("ascii")
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="public_key_ed25519_b64 must be standard Base64",
        ) from e
    if len(key) != 32:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ed25519 public key must decode to 32 bytes",
        )
    return key


@router.post(
    "/register",
    response_model=EdgeAgentRegisterResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def register_edge_agent(body: EdgeAgentRegisterBody, session: AppDbSession) -> EdgeAgentRegisterResponse:
    key_bytes = _decode_ed25519_public(body.public_key_ed25519_b64)
    r = await session.execute(
        select(EdgeAgent).where(EdgeAgent.tenant_id == body.tenant_id, EdgeAgent.device_id == body.device_id).limit(1)
    )
    existing = r.scalar_one_or_none()
    now = datetime.now(UTC)
    if existing is not None:
        if existing.public_key_ed25519 != key_bytes:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="device_id already registered with a different public key",
            )
        return EdgeAgentRegisterResponse(edge_agent_id=existing.id, registered_at=existing.registered_at)

    row = EdgeAgent(
        tenant_id=body.tenant_id,
        device_id=body.device_id,
        public_key_ed25519=key_bytes,
        registered_at=now,
        revoked_at=None,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return EdgeAgentRegisterResponse(edge_agent_id=row.id, registered_at=row.registered_at)


@router.get(
    "/by-device",
    response_model=EdgeAgentReadResponse,
    dependencies=[Depends(require_internal)],
)
async def get_edge_agent_by_device(
    session: AppDbSession,
    tenant_id: Annotated[uuid.UUID, Query(description="Tenant scope")],
    device_id: Annotated[uuid.UUID, Query(description="Stable device id from the edge agent")],
) -> EdgeAgentReadResponse:
    r = await session.execute(
        select(EdgeAgent).where(EdgeAgent.tenant_id == tenant_id, EdgeAgent.device_id == device_id).limit(1)
    )
    row = r.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="edge agent not found")
    b64 = base64.b64encode(row.public_key_ed25519).decode("ascii")
    return EdgeAgentReadResponse(
        edge_agent_id=row.id,
        tenant_id=row.tenant_id,
        device_id=row.device_id,
        public_key_ed25519_b64=b64,
        registered_at=row.registered_at,
        revoked_at=row.revoked_at,
    )
