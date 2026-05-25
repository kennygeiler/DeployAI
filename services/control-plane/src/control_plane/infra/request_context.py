"""Per-request correlation id: ContextVar + ASGI middleware that round-trips ``X-Request-ID``."""

from __future__ import annotations

import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

REQUEST_ID_HEADER = "X-Request-ID"

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)


def _coerce_or_generate(raw: str | None) -> str:
    if raw is None:
        return str(uuid.uuid4())
    candidate = raw.strip()
    if not candidate:
        return str(uuid.uuid4())
    try:
        return str(uuid.UUID(candidate))
    except ValueError:
        return str(uuid.uuid4())


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Stamp every request with a UUID correlation id, exposed via header + ContextVar."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        request_id = _coerce_or_generate(request.headers.get(REQUEST_ID_HEADER))
        token = request_id_var.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
