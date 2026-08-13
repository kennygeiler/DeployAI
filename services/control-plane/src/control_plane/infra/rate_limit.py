"""Inbound API rate limiting for the public surface (per-principal token bucket).

Scope: everything EXCEPT ``/internal/*`` (already gated by the internal key),
the health/readiness probes, and ``/metrics`` — those must never 429.

Keying: auth resolution (JWT verification, service-token lookup) happens in
route *dependencies*, i.e. after middleware has already run, so tenant_id +
subject are not resolvable here without verifying every token twice per
request. Instead the key is a sha256 of the presented credential
(``Authorization`` header, else the session access cookie) — stable per
principal for the credential's lifetime, cheap, and the raw secret is never
stored. Unauthenticated requests fall back to the client IP (first
``x-forwarded-for`` hop, then the socket peer).

Backends:

- Redis (``DEPLOYAI_REDIS_URL`` set in the process env): atomic
  INCR + PEXPIRE fixed-window counter — ``burst`` requests per 60s window.
  Not Lua because the test backend (fakeredis without lupa) cannot run
  scripts; INCR is atomic so the count never races. Redis errors fail OPEN
  (availability over enforcement) with a warning log.
- In-memory fallback: continuous-refill token bucket. Known limitation, on
  purpose: state is a process-local dict, so it only protects a single
  control-plane instance and resets on every deploy/restart (same trade-off
  as ``apps/web/src/lib/internal/demo-rate-limit.ts``). Configure
  ``DEPLOYAI_REDIS_URL`` for fleet-wide limiting.

Disabled by default: ``DEPLOYAI_API_RATE_LIMIT_PER_MINUTE`` unset or 0 makes
the middleware a pass-through.
"""

from __future__ import annotations

import hashlib
import logging
import math
import os
import time
from dataclasses import dataclass
from typing import NamedTuple

import redis.asyncio as redis
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

from control_plane.config.settings import get_settings
from control_plane.infra.metrics import _resolve_route_template
from control_plane.infra.observability import observe_rate_limited
from control_plane.infra.redis_client import get_async_redis

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60
_REDIS_KEY_PREFIX = "deployai:api-rate-limit:"

_EXEMPT_EXACT = frozenset({"/healthz", "/health", "/readyz", "/metrics"})
_EXEMPT_PREFIXES = ("/internal/",)


class RateLimitDecision(NamedTuple):
    allowed: bool
    retry_after_seconds: float


def derive_rate_limit_key(
    *,
    authorization: str | None,
    session_cookie: str | None,
    forwarded_for: str | None,
    client_host: str | None,
) -> str:
    """Stable per-principal bucket key without decoding any credential."""
    if authorization and authorization.strip():
        digest = hashlib.sha256(authorization.strip().encode()).hexdigest()
        return f"auth:{digest[:32]}"
    if session_cookie:
        digest = hashlib.sha256(session_cookie.encode()).hexdigest()
        return f"cookie:{digest[:32]}"
    if forwarded_for:
        # Only the first hop — later hops are proxy-appended and spoof-resistant
        # ordering is the ingress's job, not ours.
        first_hop = forwarded_for.split(",")[0].strip()
        if first_hop:
            return f"ip:{first_hop}"
    return f"ip:{client_host or 'unknown'}"


def is_rate_limit_exempt(path: str) -> bool:
    return path in _EXEMPT_EXACT or path.startswith(_EXEMPT_PREFIXES)


@dataclass
class _Bucket:
    tokens: float
    ts: float


class MemoryTokenBucketLimiter:
    """Continuous-refill token bucket over a process-local dict.

    Single-instance only — see module docstring for the honest limitation.
    No locking: FastAPI runs middleware on one event loop and ``check`` never
    awaits between read and write.
    """

    _SWEEP_THRESHOLD = 10_000

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}

    def check(
        self,
        key: str,
        *,
        capacity: float,
        refill_per_second: float,
        now: float,
    ) -> RateLimitDecision:
        bucket = self._buckets.get(key)
        if bucket is None:
            if len(self._buckets) >= self._SWEEP_THRESHOLD:
                self._sweep(capacity=capacity, refill_per_second=refill_per_second, now=now)
            bucket = _Bucket(tokens=capacity, ts=now)
            self._buckets[key] = bucket
        else:
            bucket.tokens = min(capacity, bucket.tokens + (now - bucket.ts) * refill_per_second)
            bucket.ts = now
        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return RateLimitDecision(True, 0.0)
        return RateLimitDecision(False, (1.0 - bucket.tokens) / refill_per_second)

    def _sweep(self, *, capacity: float, refill_per_second: float, now: float) -> None:
        # Drop buckets whose elapsed idle time refilled them to capacity —
        # indistinguishable from a fresh bucket, so the map stays bounded.
        full_after = capacity / refill_per_second
        stale = [k for k, b in self._buckets.items() if now - b.ts >= full_after]
        for k in stale:
            del self._buckets[k]

    def reset(self) -> None:
        self._buckets.clear()


_memory_limiter = MemoryTokenBucketLimiter()


def reset_rate_limiter_state() -> None:
    """Test helper: clear the in-memory buckets (Redis state lives in Redis)."""
    _memory_limiter.reset()


async def redis_fixed_window_check(
    client: redis.Redis,
    key: str,
    *,
    budget: int,
    window_seconds: int = _WINDOW_SECONDS,
) -> RateLimitDecision:
    """Atomic fixed-window counter: ``budget`` requests per window per key.

    INCR is atomic, so concurrent instances never double-admit. The window
    starts at the first request and ends when the key expires.
    """
    redis_key = f"{_REDIS_KEY_PREFIX}{key}"
    window_ms = window_seconds * 1000
    count = int(await client.incr(redis_key))
    if count == 1:
        await client.pexpire(redis_key, window_ms)
    if count <= budget:
        return RateLimitDecision(True, 0.0)
    ttl_ms = int(await client.pttl(redis_key))
    if ttl_ms < 0:
        # TTL lost (crash between INCR and PEXPIRE) — re-arm so the key
        # cannot deny forever.
        await client.pexpire(redis_key, window_ms)
        ttl_ms = window_ms
    return RateLimitDecision(False, ttl_ms / 1000.0)


def _redis_configured() -> bool:
    # `settings.redis_url` carries a dev default, so field presence cannot
    # distinguish "operator configured Redis" — the process env var is the
    # opt-in signal.
    return bool(os.environ.get("DEPLOYAI_REDIS_URL"))


class RateLimitMiddleware(BaseHTTPMiddleware):
    """429 + Retry-After once a principal exhausts its token bucket."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Settings are read per-request: the app object is a module singleton
        # and tests re-point env vars + clear_settings_cache() after import.
        settings = get_settings()
        per_minute = settings.api_rate_limit_per_minute
        if per_minute <= 0 or is_rate_limit_exempt(request.url.path):
            return await call_next(request)

        burst = settings.api_rate_limit_burst
        capacity = burst if burst is not None and burst > 0 else per_minute
        key = derive_rate_limit_key(
            authorization=request.headers.get("authorization"),
            session_cookie=request.cookies.get(settings.session_access_cookie),
            forwarded_for=request.headers.get("x-forwarded-for"),
            client_host=request.client.host if request.client else None,
        )

        if _redis_configured():
            try:
                decision = await redis_fixed_window_check(
                    get_async_redis(),
                    key,
                    budget=capacity,
                )
            except Exception:
                logger.warning(
                    "api_rate_limit.redis_unavailable — failing open",
                    exc_info=True,
                )
                decision = RateLimitDecision(True, 0.0)
        else:
            decision = _memory_limiter.check(
                key,
                capacity=float(capacity),
                refill_per_second=per_minute / 60.0,
                now=time.monotonic(),
            )

        if decision.allowed:
            return await call_next(request)

        observe_rate_limited(_resolve_route_template(request))
        return JSONResponse(
            status_code=429,
            content={"error": "rate_limited"},
            headers={"Retry-After": str(max(1, math.ceil(decision.retry_after_seconds)))},
        )
