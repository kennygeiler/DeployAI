"""Prometheus text exposition (protected by internal API key)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Response

from control_plane.config.internal_auth import require_internal
from control_plane.infra.observability import metrics_payload

router = APIRouter(prefix="/metrics", tags=["internal-metrics"])


@router.get("", dependencies=[Depends(require_internal)])
async def prometheus_metrics() -> Response:
    body, ct = metrics_payload()
    if not body:
        return Response(
            b"# prometheus_client unavailable or no registry\n",
            media_type="text/plain",
        )
    return Response(content=body, media_type=ct)
