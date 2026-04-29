"""Epic 16 — pilot morning digest + evidence nodes (file-backed tenant scope until canonical APIs)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from control_plane.config.internal_api import verify_internal_key
from control_plane.services.pilot_surface_data import (
    pilot_digest_items_for_tenant,
    pilot_evening_synthesis_payload_for_tenant,
    pilot_evidence_item_for_tenant,
    pilot_phase_tracking_rows_for_tenant,
)

router = APIRouter(prefix="/strategist/pilot-surfaces", tags=["internal-strategist-pilot"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


class MorningDigestTopRead(BaseModel):
    items: list[Any]
    provenance: str = "pilot_surface_file"


class PhaseTrackingRead(BaseModel):
    items: list[Any]
    provenance: str = "pilot_surface_file"


class EveningSynthesisRead(BaseModel):
    candidates: list[Any]
    patterns: list[Any] = Field(default_factory=list)
    provenance: str = "pilot_surface_file"


@router.get(
    "/morning-digest-top",
    response_model=MorningDigestTopRead,
    dependencies=[Depends(require_internal)],
)
async def read_morning_digest_top(
    tenant_id: Annotated[uuid.UUID, Query(description="Tenant scope for digest rows.")],
) -> MorningDigestTopRead:
    tid = str(tenant_id)
    rows = pilot_digest_items_for_tenant(tid)
    if rows is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pilot digest data configured for this tenant",
        )
    return MorningDigestTopRead(items=rows)


@router.get(
    "/phase-tracking",
    response_model=PhaseTrackingRead,
    dependencies=[Depends(require_internal)],
)
async def read_phase_tracking(
    tenant_id: Annotated[uuid.UUID, Query(description="Tenant scope for phase-tracking rows.")],
) -> PhaseTrackingRead:
    tid = str(tenant_id)
    rows = pilot_phase_tracking_rows_for_tenant(tid)
    if rows is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pilot phase-tracking data configured for this tenant",
        )
    return PhaseTrackingRead(items=rows)


@router.get(
    "/evening-synthesis",
    response_model=EveningSynthesisRead,
    dependencies=[Depends(require_internal)],
)
async def read_evening_synthesis(
    tenant_id: Annotated[uuid.UUID, Query(description="Tenant scope for evening synthesis payload.")],
) -> EveningSynthesisRead:
    tid = str(tenant_id)
    raw = pilot_evening_synthesis_payload_for_tenant(tid)
    if raw is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No pilot evening synthesis data configured for this tenant",
        )
    cand = raw.get("candidates")
    if not isinstance(cand, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="evening_synthesis.candidates must be a JSON array",
        )
    pat = raw.get("patterns", [])
    if pat is None:
        pat = []
    if not isinstance(pat, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="evening_synthesis.patterns must be a JSON array when present",
        )
    return EveningSynthesisRead(candidates=cand, patterns=pat)


@router.get(
    "/evidence-node/{node_id}",
    dependencies=[Depends(require_internal)],
)
async def read_evidence_node(
    node_id: str,
    tenant_id: Annotated[uuid.UUID, Query(description="Tenant scope for evidence node.")],
) -> dict[str, Any]:
    tid = str(tenant_id)
    item = pilot_evidence_item_for_tenant(tid, node_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evidence node not found")
    return item
