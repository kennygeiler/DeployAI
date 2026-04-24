"""FastAPI entrypoint for the DeployAI Control Plane.

Story 1.3 shipped the liveness probe. Story 1.7 adds the `/health` alias
for the docker-compose healthcheck (AC matches the literal `/health`
path in the epic). Real routes land in Stories 1.9+ (tenant isolation,
authz) and Epic 5 (compliance + audit).
"""

from __future__ import annotations

from importlib import metadata

from fastapi import FastAPI

from control_plane.api.routes.auth import router as auth_router
from control_plane.api.routes.internal_session import router as internal_session_router
from control_plane.api.routes.platform import router as platform_router
from control_plane.api.routes.schema_proposals import router as schema_proposals_internal_router
from control_plane.api.routes.scim import router as scim_users_router

try:
    _version = metadata.version("control-plane")
except metadata.PackageNotFoundError:  # editable/unbuilt installs
    _version = "0.0.0-scaffold"

app = FastAPI(title="DeployAI Control Plane", version=_version)
app.include_router(auth_router)
app.include_router(platform_router)
app.include_router(schema_proposals_internal_router, prefix="/internal/v1")
app.include_router(internal_session_router, prefix="/internal/v1")
app.include_router(scim_users_router, prefix="/scim/v2")


def _health_body() -> dict[str, str]:
    return {"status": "ok", "service": "control-plane", "version": _version}


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness probe (k8s convention). Used by docker-compose (Story 1.7)."""
    return _health_body()


@app.get("/health")
async def health() -> dict[str, str]:
    """Alias of `/healthz`. Satisfies Story 1.7 AC literal `/health`."""
    return _health_body()
