"""Prometheus text exposition (protected by internal API key)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Response, status

from control_plane.config.internal_api import verify_internal_key
from control_plane.infra.observability import metrics_payload

router = APIRouter(prefix="/metrics", tags=["internal-metrics"])


def require_internal(
    x_deployai_internal_key: str | None = Header(default=None, alias="X-DeployAI-Internal-Key"),
) -> None:
    if not verify_internal_key(x_deployai_internal_key):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-DeployAI-Internal-Key",
        )


@router.get("", dependencies=[Depends(require_internal)])
async def prometheus_metrics() -> Response:
    body, ct = metrics_payload()
    if not body:
        return Response(
            b"# prometheus_client unavailable or no registry\n",
            media_type="text/plain",
        )
    return Response(content=body, media_type=ct)
