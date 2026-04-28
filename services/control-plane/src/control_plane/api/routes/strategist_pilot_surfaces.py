"""Epic 16 — pilot morning digest + evidence nodes (file-backed tenant scope until canonical APIs)."""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from control_plane.config.internal_api import verify_internal_key
from control_plane.services.pilot_surface_data import (
    pilot_digest_items_for_tenant,
    pilot_evidence_item_for_tenant,
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
