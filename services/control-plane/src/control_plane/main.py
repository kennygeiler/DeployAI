"""FastAPI entrypoint for the DeployAI Control Plane.

Story 1.3 shipped the liveness probe. Story 1.7 adds the `/health` alias
for the docker-compose healthcheck (AC matches the literal `/health`
path in the epic). Real routes land in Stories 1.9+ (tenant isolation,
authz) and Epic 5 (compliance + audit).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from importlib import metadata

from fastapi import FastAPI

import control_plane.bootstrap  # noqa: F401  # configure OTel before other control_plane imports
from control_plane.api.routes.adjudication_queue import router as adjudication_queue_internal_router
from control_plane.api.routes.auth import router as auth_router
from control_plane.api.routes.auth_oidc import auth_entry_router, oidc_router
from control_plane.api.routes.auth_saml import router as auth_saml_router
from control_plane.api.routes.break_glass import router as break_glass_router
from control_plane.api.routes.ingestion_runs import router as ingestion_runs_internal_router
from control_plane.api.routes.integrations import router as integrations_router
from control_plane.api.routes.integrations_google_gmail import (
    router as integrations_google_gmail_router,
)
from control_plane.api.routes.integrations_m365_calendar import (
    router as integrations_m365_calendar_router,
)
from control_plane.api.routes.integrations_m365_mail import (
    router as integrations_m365_mail_router,
)
from control_plane.api.routes.integrations_m365_teams import (
    router as integrations_m365_teams_router,
)
from control_plane.api.routes.integrations_slack import (
    router as integrations_slack_router,
)
from control_plane.api.routes.internal_metrics import router as internal_metrics_router
from control_plane.api.routes.internal_session import router as internal_session_router
from control_plane.api.routes.phase_transitions import router as phase_transitions_internal_router
from control_plane.api.routes.platform import router as platform_router
from control_plane.api.routes.schema_proposals import router as schema_proposals_internal_router
from control_plane.api.routes.scim import router as scim_users_router
from control_plane.api.routes.upload_artifacts import router as upload_artifacts_router

try:
    _version = metadata.version("control-plane")
except metadata.PackageNotFoundError:  # editable/unbuilt installs
    _version = "0.0.0-scaffold"


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    from control_plane.otel import shutdown_opentelemetry

    try:
        yield
    finally:
        shutdown_opentelemetry()


app = FastAPI(title="DeployAI Control Plane", version=_version, lifespan=_lifespan)
app.include_router(auth_router)
app.include_router(oidc_router)
app.include_router(auth_entry_router)
app.include_router(auth_saml_router)
app.include_router(break_glass_router)
app.include_router(integrations_router)
app.include_router(integrations_m365_calendar_router)
app.include_router(integrations_m365_mail_router)
app.include_router(integrations_m365_teams_router)
app.include_router(integrations_google_gmail_router)
app.include_router(integrations_slack_router)
app.include_router(upload_artifacts_router)
app.include_router(platform_router)
app.include_router(schema_proposals_internal_router, prefix="/internal/v1")
app.include_router(ingestion_runs_internal_router, prefix="/internal/v1")
app.include_router(adjudication_queue_internal_router, prefix="/internal/v1")
app.include_router(phase_transitions_internal_router, prefix="/internal/v1")
app.include_router(internal_metrics_router, prefix="/internal/v1")
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
