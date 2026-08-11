from __future__ import annotations

import asyncio
import email.utils
import hashlib
import random
import time
from collections.abc import Awaitable, Callable
from datetime import UTC
from typing import Any

import httpx

DEFAULT_CAPS: dict[str, bool] = {
    "extraction": True,
    "retrieval": True,
    "arbitration": True,
    "embeddings": True,
    "tool_use": True,
}

UsageCallback = Callable[[dict[str, Any]], None]

# Retry policy defaults, shared by the sync and async helpers.
DEFAULT_MAX_ATTEMPTS = 4
DEFAULT_BASE_DELAY_S = 0.15
DEFAULT_MAX_DELAY_S = 30.0
DEFAULT_MAX_ELAPSED_S = 120.0

# Connect-phase failures are safe to retry: the request never reached the
# server, so retrying cannot duplicate work.
CONNECT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout)


def record_usage(
    callback: UsageCallback | None,
    payload: dict[str, Any],
) -> None:
    if callback is not None:
        callback(payload)
    from llm_provider_py.telemetry import emit_llm_usage_metrics

    emit_llm_usage_metrics(payload)


def pseudo_embed(text: str, dim: int = 256) -> list[float]:
    """Deterministic low-dimensional embedding (tests / offline). Not for prod retrieval quality."""
    h = hashlib.blake2b(text.encode("utf-8"), digest_size=32).digest()
    return [((h[i % 32] + (i * 7)) % 256) / 255.0 for i in range(dim)]


def is_retryable_status(status: int) -> bool:
    """429 (rate limit) and 5xx (transient server failure) are retryable."""
    return status == 429 or status >= 500


def parse_retry_after(value: str | None, *, now: Callable[[], float] = time.time) -> float | None:
    """Parse a ``Retry-After`` header value into seconds.

    Supports both RFC 9110 forms: delay-seconds (``"3"``) and HTTP-date
    (``"Fri, 31 Dec 1999 23:59:59 GMT"``). Returns ``None`` for missing or
    unparseable values; results clamp to >= 0 (a date in the past means
    "retry now", not "sleep a negative amount").
    """
    if not value:
        return None
    v = value.strip()
    try:
        return max(0.0, float(v))
    except ValueError:
        pass
    try:
        dt = email.utils.parsedate_to_datetime(v)
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return max(0.0, dt.timestamp() - now())


def compute_backoff_delay(
    attempt: int,
    *,
    base_delay_s: float = DEFAULT_BASE_DELAY_S,
    max_delay_s: float = DEFAULT_MAX_DELAY_S,
    retry_after_s: float | None = None,
    rand: Callable[[], float] = random.random,
) -> float:
    """Pure backoff computation: exponential growth with full jitter.

    The delay before retry ``attempt`` (0-based) is drawn uniformly from
    ``[0, min(max_delay_s, base_delay_s * 2**attempt)]`` — "full jitter",
    which decorrelates retry storms across concurrent callers far better
    than a fixed exponential schedule. When the server sent ``Retry-After``,
    that value acts as a floor: we never retry earlier than the server
    asked, but the result is still capped at ``max_delay_s`` so a hostile
    or buggy header cannot stall us for minutes.

    Pure function: inject ``rand`` for deterministic tests.
    """
    ceiling = min(max_delay_s, base_delay_s * (2.0**attempt))
    delay = rand() * ceiling
    if retry_after_s is not None:
        delay = min(max(delay, retry_after_s), max_delay_s)
    return delay


def httpx_post_with_retries(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str],
    json: Any,
    max_retries: int = DEFAULT_MAX_ATTEMPTS,
    rand: Callable[[], float] = random.random,
    sleep: Callable[[float], None] = time.sleep,
) -> httpx.Response:
    """Sync POST with retries on 429/5xx.

    Exponential backoff with full jitter; honors ``Retry-After``. Other
    statuses (and the final failing attempt) return immediately.
    """
    last: httpx.Response | None = None
    for attempt in range(max_retries):
        r = client.post(url, headers=headers, json=json)
        last = r
        if not is_retryable_status(r.status_code):
            return r
        if attempt >= max_retries - 1:
            return r
        sleep(
            compute_backoff_delay(
                attempt,
                retry_after_s=parse_retry_after(r.headers.get("retry-after")),
                rand=rand,
            )
        )
    assert last is not None
    return last


async def httpx_post_with_retries_async(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    json: Any,
    max_retries: int = DEFAULT_MAX_ATTEMPTS,
    max_elapsed_s: float = DEFAULT_MAX_ELAPSED_S,
    rand: Callable[[], float] = random.random,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> httpx.Response:
    """Async POST with retries on 429/5xx and connect-phase errors.

    Exponential backoff with full jitter; honors ``Retry-After``; gives up
    when attempts are exhausted or when the next sleep would push the total
    elapsed time past ``max_elapsed_s``. On give-up the last response is
    returned (caller inspects the status) or the last connect error is
    re-raised.
    """
    started = time.monotonic()
    last_exc: httpx.TransportError | None = None
    last: httpx.Response | None = None
    for attempt in range(max_retries):
        retry_after: float | None = None
        try:
            r = await client.post(url, headers=headers, json=json)
        except CONNECT_ERRORS as exc:
            last_exc = exc
            last = None
        else:
            last_exc = None
            last = r
            if not is_retryable_status(r.status_code):
                return r
            retry_after = parse_retry_after(r.headers.get("retry-after"))
        if attempt >= max_retries - 1:
            break
        delay = compute_backoff_delay(attempt, retry_after_s=retry_after, rand=rand)
        if (time.monotonic() - started) + delay > max_elapsed_s:
            break
        await sleep(delay)
    if last is not None:
        return last
    assert last_exc is not None
    raise last_exc


async def httpx_stream_open_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    json: Any,
    max_retries: int = DEFAULT_MAX_ATTEMPTS,
    max_elapsed_s: float = DEFAULT_MAX_ELAPSED_S,
    rand: Callable[[], float] = random.random,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> httpx.Response:
    """Open a streaming POST, retrying ONLY the initial connection.

    Retries cover connect-phase errors and 429/5xx statuses observed
    before any body bytes reach the caller. Once a response is returned
    from here and the caller starts consuming the stream, NO retry is
    possible: SSE events already yielded downstream may have had side
    effects (partial text shown to a user, usage telemetry emitted), so
    replaying the request would duplicate them. Mid-stream failures must
    surface to the caller as errors instead.

    The returned response has an open stream; the caller owns closing it
    (``await resp.aclose()``). A still-failing final response is returned
    open so the caller can ``aread()`` the error body.
    """
    started = time.monotonic()
    last_exc: httpx.TransportError | None = None
    resp: httpx.Response | None = None
    for attempt in range(max_retries):
        retry_after: float | None = None
        try:
            request = client.build_request("POST", url, headers=headers, json=json)
            resp = await client.send(request, stream=True)
        except CONNECT_ERRORS as exc:
            last_exc = exc
            resp = None
        else:
            last_exc = None
            if not is_retryable_status(resp.status_code):
                return resp
            retry_after = parse_retry_after(resp.headers.get("retry-after"))
        if attempt >= max_retries - 1:
            break
        delay = compute_backoff_delay(attempt, retry_after_s=retry_after, rand=rand)
        if (time.monotonic() - started) + delay > max_elapsed_s:
            break
        if resp is not None:
            await resp.aclose()
        await sleep(delay)
    if resp is not None:
        return resp
    assert last_exc is not None
    raise last_exc
