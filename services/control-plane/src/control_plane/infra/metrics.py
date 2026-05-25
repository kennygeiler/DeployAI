"""Prometheus metrics + HTTP middleware for the D1.d perf budget."""

from __future__ import annotations

import time
from contextvars import ContextVar
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
_UNKNOWN_METHOD = "UNKNOWN"

# ContextVars set by PrometheusMiddleware for the duration of each request.
# The `engine_connect` listener copies them onto `connection.info`, which the
# `after_cursor_execute` listener reads — `connection.info` is the only state
# guaranteed to be visible inside SQLAlchemy's cursor worker thread.
_route_var: ContextVar[str] = ContextVar("deployai_route", default=_UNKNOWN_ROUTE)
_method_var: ContextVar[str] = ContextVar("deployai_method", default=_UNKNOWN_METHOD)

_CONN_INFO_ROUTE_KEY = "deployai_route"
_CONN_INFO_METHOD_KEY = "deployai_method"

db_statements_total = Counter(
    "deployai_db_statements_total",
    "SQLAlchemy statements executed, labelled by request route + method.",
    ("route", "method"),
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
        route_token = _route_var.set(route)
        method_token = _method_var.set(method)
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
            _route_var.reset(route_token)
            _method_var.reset(method_token)


def _on_engine_connect(connection: Any) -> None:
    # Pooled connections retain `info` across checkouts; overwrite on every
    # checkout so a previous request's labels never bleed into the next one.
    connection.info[_CONN_INFO_ROUTE_KEY] = _route_var.get()
    connection.info[_CONN_INFO_METHOD_KEY] = _method_var.get()


def _after_cursor_execute(
    _conn: Any,
    _cursor: Any,
    _statement: str,
    _parameters: Any,
    context: Any,
    _executemany: bool,
) -> None:
    info = context.connection.info if context is not None else {}
    route = info.get(_CONN_INFO_ROUTE_KEY, _UNKNOWN_ROUTE)
    method = info.get(_CONN_INFO_METHOD_KEY, _UNKNOWN_METHOD)
    db_statements_total.labels(route=route, method=method).inc()


def install_db_statement_listener(engine: Engine | Any) -> None:
    """Idempotently attach the per-statement counter to ``engine``.

    Accepts an :class:`AsyncEngine` and unwraps its sync facade so the listener
    fires inside the worker thread that actually runs the cursor.
    """
    target = getattr(engine, "sync_engine", engine)
    if not event.contains(target, "engine_connect", _on_engine_connect):
        event.listen(target, "engine_connect", _on_engine_connect)
    if not event.contains(target, "after_cursor_execute", _after_cursor_execute):
        event.listen(target, "after_cursor_execute", _after_cursor_execute)
