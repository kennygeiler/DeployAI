"""Explicit OpenTelemetry tracing: server spans, agent-turn spans, W3C propagation.

No auto-instrumentation on purpose — one small ASGI middleware makes the
server span, the agent nodes open their own spans, and outbound HTTP
injects ``traceparent`` by hand, so every span in a trace is greppable to
the line that created it. When no tracer provider is configured
(``DEPLOYAI_OTEL_EXPORTER_OTLP_ENDPOINT`` unset — see ``control_plane.otel``)
``trace.get_tracer`` hands out non-recording spans and every helper here
is a cheap no-op.
"""

from __future__ import annotations

import functools
from collections.abc import Awaitable, Callable
from typing import Any, ParamSpec, TypeVar

from opentelemetry import trace
from opentelemetry.trace import SpanKind, format_trace_id
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from control_plane.infra.metrics import _resolve_route_template
from control_plane.infra.request_context import request_id_var, trace_id_var

_SCOPE_NAME = "deployai.control-plane"

# W3C tracecontext only (no baggage): the only propagation contract with the
# web BFF is the ``traceparent`` header.
_PROPAGATOR = TraceContextTextMapPropagator()

# Unit tests point span helpers at a local SDK TracerProvider with an
# InMemorySpanExporter WITHOUT touching the process-global provider
# (``trace.set_tracer_provider`` is once-per-process). Production never
# sets this — ``None`` means "use the global provider".
_provider_override: Any | None = None

_P = ParamSpec("_P")
_R = TypeVar("_R")


def set_tracer_provider_override(provider: Any | None) -> None:
    """Test hook: route ``tracer()`` through ``provider`` (``None`` restores global)."""
    global _provider_override
    _provider_override = provider


def tracer() -> trace.Tracer:
    """Resolve the shared tracer at call time so a late-installed provider is honored."""
    if _provider_override is not None:
        return trace.get_tracer(_SCOPE_NAME, tracer_provider=_provider_override)
    return trace.get_tracer(_SCOPE_NAME)


def traced(name: str) -> Callable[[Callable[_P, Awaitable[_R]]], Callable[_P, Awaitable[_R]]]:
    """Wrap an async function in a span; the body reaches it via ``trace.get_current_span()``.

    Exceptions are recorded on the span and re-raised (the SDK default for
    ``start_as_current_span``).
    """

    def decorate(fn: Callable[_P, Awaitable[_R]]) -> Callable[_P, Awaitable[_R]]:
        @functools.wraps(fn)
        async def wrapper(*args: _P.args, **kwargs: _P.kwargs) -> _R:
            with tracer().start_as_current_span(name):
                return await fn(*args, **kwargs)

        return wrapper

    return decorate


def inject_trace_context(headers: dict[str, str]) -> None:
    """Stamp the current span's W3C ``traceparent`` onto outbound request headers."""
    _PROPAGATOR.inject(headers)


class TracingMiddleware(BaseHTTPMiddleware):
    """One SERVER span per request, child of any inbound ``traceparent``.

    Installed only when trace export is configured (see ``main.py``) so the
    default deployment carries zero per-request overhead. Must sit INSIDE
    ``RequestIdMiddleware`` — the request id ContextVar has to be populated
    before the span attributes are stamped.
    """

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        parent = _PROPAGATOR.extract(carrier=request.headers)
        route = _resolve_route_template(request)
        with tracer().start_as_current_span(
            f"{request.method} {route}",
            context=parent,
            kind=SpanKind.SERVER,
        ) as span:
            ctx = span.get_span_context()
            trace_token = trace_id_var.set(format_trace_id(ctx.trace_id) if ctx.is_valid else None)
            try:
                span.set_attribute("http.method", request.method)
                span.set_attribute("http.route", route)
                request_id = request_id_var.get()
                if request_id is not None:
                    span.set_attribute("deployai.request_id", request_id)
                status_code = 500
                try:
                    response = await call_next(request)
                    status_code = response.status_code
                finally:
                    span.set_attribute("http.status_code", status_code)
                return response
            finally:
                trace_id_var.reset(trace_token)


__all__ = [
    "TracingMiddleware",
    "inject_trace_context",
    "set_tracer_provider_override",
    "traced",
    "tracer",
]
