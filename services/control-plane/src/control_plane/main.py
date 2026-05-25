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
from fastapi.responses import JSONResponse, Response
from prometheus_client import REGISTRY, generate_latest
from sqlalchemy import text

import control_plane.bootstrap  # noqa: F401  # configure logging + OTel before other control_plane imports
from control_plane.api.routes.adjudication_queue import router as adjudication_queue_internal_router
from control_plane.api.routes.audit_internal import router as audit_internal_router
from control_plane.api.routes.auth import router as auth_router
from control_plane.api.routes.auth_oidc import auth_entry_router, oidc_router
from control_plane.api.routes.auth_saml import router as auth_saml_router
from control_plane.api.routes.break_glass import router as break_glass_router
from control_plane.api.routes.emails_internal import router as emails_internal_router
from control_plane.api.routes.engagement_events import router as engagement_events_router
from control_plane.api.routes.engagement_recommendations import router as engagement_recommendations_router
from control_plane.api.routes.engagement_timeline import router as engagement_timeline_router
from control_plane.api.routes.engagements_internal import router as engagements_internal_router
from control_plane.api.routes.event_search import router as event_search_router
from control_plane.api.routes.extract_preview import router as extract_preview_router
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
from control_plane.api.routes.ledger_internal import router as ledger_internal_router
from control_plane.api.routes.meetings_internal import router as meetings_internal_router
from control_plane.api.routes.phase_transitions import router as phase_transitions_internal_router
from control_plane.api.routes.platform import router as platform_router
from control_plane.api.routes.schema_proposals import router as schema_proposals_internal_router
from control_plane.api.routes.scim import router as scim_users_router
from control_plane.api.routes.strategist_integration_records import (
    router as strategist_integration_records_internal_router,
)
from control_plane.api.routes.strategist_meeting_presence import (
    router as strategist_meeting_presence_internal_router,
)
from control_plane.api.routes.strategist_overrides import router as strategist_overrides_internal_router
from control_plane.api.routes.strategist_pilot_surfaces import (
    router as strategist_pilot_surfaces_internal_router,
)
from control_plane.api.routes.strategist_queues_internal import router as strategist_queues_internal_router
from control_plane.api.routes.temporal_insights_internal import (
    intelligence_router as temporal_intelligence_router,
)
from control_plane.api.routes.temporal_insights_internal import (
    router as temporal_insights_internal_router,
)
from control_plane.api.routes.tenants_internal import router as tenants_internal_router
from control_plane.api.routes.upload_artifacts import router as upload_artifacts_router
from control_plane.api.routes.webhooks_internal import router as webhooks_internal_router
from control_plane.infra.metrics import PrometheusMiddleware
from control_plane.infra.request_context import RequestIdMiddleware

try:
    _version = metadata.version("control-plane")
except metadata.PackageNotFoundError:  # editable/unbuilt installs
    _version = "0.0.0-scaffold"


@asynccontextmanager
async def _lifespan(_: FastAPI) -> AsyncIterator[None]:
    from control_plane.db import get_engine
    from control_plane.infra.metrics import install_db_statement_listener
    from control_plane.otel import shutdown_opentelemetry

    install_db_statement_listener(get_engine())
    try:
        yield
    finally:
        shutdown_opentelemetry()


app = FastAPI(title="DeployAI Control Plane", version=_version, lifespan=_lifespan)
app.add_middleware(PrometheusMiddleware)
# Added last so it wraps PrometheusMiddleware — the request_id is set in the
# ContextVar before prometheus observes the request.
app.add_middleware(RequestIdMiddleware)
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
app.include_router(strategist_meeting_presence_internal_router, prefix="/internal/v1")
app.include_router(strategist_pilot_surfaces_internal_router, prefix="/internal/v1")
app.include_router(strategist_overrides_internal_router, prefix="/internal/v1")
app.include_router(strategist_integration_records_internal_router, prefix="/internal/v1")
app.include_router(strategist_queues_internal_router, prefix="/internal/v1")
app.include_router(engagements_internal_router, prefix="/internal/v1")
app.include_router(engagement_events_router, prefix="/internal/v1")
app.include_router(engagement_recommendations_router, prefix="/internal/v1")
app.include_router(event_search_router, prefix="/internal/v1")
app.include_router(extract_preview_router, prefix="/internal/v1")
app.include_router(engagement_timeline_router, prefix="/internal/v1")
app.include_router(ledger_internal_router, prefix="/internal/v1")
app.include_router(temporal_insights_internal_router, prefix="/internal/v1")
app.include_router(temporal_intelligence_router, prefix="/internal/v1")
app.include_router(tenants_internal_router, prefix="/internal/v1")
app.include_router(audit_internal_router, prefix="/internal/v1")
app.include_router(webhooks_internal_router, prefix="/internal/v1")
app.include_router(meetings_internal_router, prefix="/internal/v1")
app.include_router(emails_internal_router, prefix="/internal/v1")
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


@app.get("/readyz")
async def readyz() -> JSONResponse:
    """Readiness probe (k8s convention). Checks DB connectivity."""
    from control_plane.db import get_engine

    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        return JSONResponse(
            status_code=503,
            content={"status": "not-ready", "reason": type(exc).__name__},
        )
    return JSONResponse(status_code=200, content={"status": "ready"})


@app.get("/metrics")
async def metrics_endpoint() -> Response:
    """Prometheus scrape endpoint. Wire to the default process registry."""
    return Response(
        content=generate_latest(REGISTRY),
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )
