"""Prometheus metrics + HTTP middleware for the D1.d perf budget."""

from __future__ import annotations

import time
from typing import Any

from prometheus_client import Counter, Histogram
from sqlalchemy import event
from sqlalchemy.engine import Engine
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.routing import Match
from starlette.types import ASGIApp

SLOW_REQUEST_SECONDS = 1.0

_UNKNOWN_ROUTE = "unknown"

# Unlabelled: the SQLAlchemy after_cursor_execute event fires in a worker
# thread; FastAPI request-scope ContextVars set in the middleware aren't
# visible there, so attaching route/method labels would always emit defaults.
# Aggregate counter + the per-request histogram (with labels) together cover
# the budget: scrape both, divide statements-rate by request-rate for an
# average. If per-route attribution becomes a real need, the proper fix is
# to set the route on the connection via `engine_connect` event hook.
db_statements_total = Counter(
    "deployai_db_statements_total",
    "SQLAlchemy statements executed across all requests + background jobs.",
)

http_request_duration_seconds = Histogram(
    "deployai_http_request_duration_seconds",
    "HTTP request duration in seconds, labelled by route, method, and status.",
    ("route", "method", "status"),
)

audit_emit_failures_total = Counter(
    "deployai_audit_emit_failures_total",
    "Exceptions raised inside emit_audit_event before successful flush.",
)

slow_request_total = Counter(
    "deployai_slow_request_total",
    f"HTTP requests whose total duration exceeded {SLOW_REQUEST_SECONDS:.0f}s.",
    ("route",),
)


def _resolve_route_template(request: Request) -> str:
    """Walk the app's router tree to find the matching route template.

    Raw paths (e.g. ``/internal/v1/engagements/<uuid>``) would explode label
    cardinality; the template (``/internal/v1/engagements/{engagement_id}``)
    keeps it bounded.
    """
    router = request.app.router
    for route in router.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", _UNKNOWN_ROUTE) or _UNKNOWN_ROUTE
    return _UNKNOWN_ROUTE


class PrometheusMiddleware(BaseHTTPMiddleware):
    """Time each request, observe a histogram, count slow ones."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        route = _resolve_route_template(request)
        method = request.method
        start = time.perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            http_request_duration_seconds.labels(
                route=route,
                method=method,
                status=str(status_code),
            ).observe(duration)
            if duration > SLOW_REQUEST_SECONDS:
                slow_request_total.labels(route=route).inc()


def _after_cursor_execute(
    _conn: Any,
    _cursor: Any,
    _statement: str,
    _parameters: Any,
    _context: Any,
    _executemany: bool,
) -> None:
    db_statements_total.inc()


def install_db_statement_listener(engine: Engine | Any) -> None:
    """Idempotently attach the per-statement counter to ``engine``.

    Accepts an :class:`AsyncEngine` and unwraps its sync facade so the listener
    fires inside the worker thread that actually runs the cursor.
    """
    target = getattr(engine, "sync_engine", engine)
    if event.contains(target, "after_cursor_execute", _after_cursor_execute):
        return
    event.listen(target, "after_cursor_execute", _after_cursor_execute)
