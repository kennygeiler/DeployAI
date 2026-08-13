from __future__ import annotations

import asyncio
import email.utils
import hashlib
import logging
import random
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import UTC
from typing import Any, NoReturn

import httpx

logger = logging.getLogger(__name__)

DEFAULT_CAPS: dict[str, bool] = {
    "extraction": True,
    "retrieval": True,
    "arbitration": True,
    "embeddings": True,
    "tool_use": True,
}

UsageCallback = Callable[[dict[str, Any]], None]

# Retry policy defaults, shared by the sync and async helpers.
# Attempts, not retries-after-first: 3 attempts == up to 2 retries.
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_BASE_DELAY_S = 1.0
DEFAULT_MAX_DELAY_S = 30.0
DEFAULT_MAX_ELAPSED_S = 120.0

# Transient network failures. Chat requests are idempotent from the caller's
# view (a duplicated completion wastes tokens, never corrupts state), so
# timeouts and dropped connections are retryable alongside connect-phase
# errors. LocalProtocolError / UnsupportedProtocol stay non-retryable: those
# are client bugs a retry would only hide. Streaming callers additionally
# gate retries on the first body chunk — see httpx_stream_bytes_with_retries.
RETRYABLE_TRANSPORT_ERRORS: tuple[type[httpx.TransportError], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.ReadError,
    httpx.WriteTimeout,
    httpx.WriteError,
    httpx.PoolTimeout,
    httpx.RemoteProtocolError,
)


def _log_retry(
    attempt: int,
    delay: float,
    *,
    status: int | None = None,
    exc: BaseException | None = None,
) -> None:
    cause = f"status {status}" if status is not None else repr(exc)
    logger.warning(
        "retrying LLM HTTP request: attempt %d failed (%s), sleeping %.2fs",
        attempt + 1,
        cause,
        delay,
    )


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
    """429 (rate limit) and 5xx — incl. 529 overloaded_error — are retryable.

    Other 4xx are never retried: the request itself is invalid, so a retry
    burns quota and hides the bug.
    """
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
    """Sync POST with retries on 429/5xx and retryable transport errors.

    Exponential backoff with full jitter; honors ``Retry-After``. Other
    statuses (and the final failing attempt) return immediately; on
    transport-error exhaustion the last error is re-raised.
    """
    attempts = max(max_retries, 1)
    last_exc: httpx.TransportError | None = None
    last: httpx.Response | None = None
    for attempt in range(attempts):
        retry_after: float | None = None
        status: int | None = None
        try:
            r = client.post(url, headers=headers, json=json)
        except RETRYABLE_TRANSPORT_ERRORS as exc:
            last_exc = exc
            last = None
        else:
            last_exc = None
            last = r
            status = r.status_code
            if not is_retryable_status(status):
                return r
            retry_after = parse_retry_after(r.headers.get("retry-after"))
        if attempt >= attempts - 1:
            break
        delay = compute_backoff_delay(attempt, retry_after_s=retry_after, rand=rand)
        _log_retry(attempt, delay, status=status, exc=last_exc)
        sleep(delay)
    if last is not None:
        return last
    assert last_exc is not None
    raise last_exc


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
    """Async POST with retries on 429/5xx and retryable transport errors.

    Exponential backoff with full jitter; honors ``Retry-After``; gives up
    when attempts are exhausted or when the next sleep would push the total
    elapsed time past ``max_elapsed_s``. On give-up the last response is
    returned (caller inspects the status) or the last transport error is
    re-raised.
    """
    started = time.monotonic()
    attempts = max(max_retries, 1)
    last_exc: httpx.TransportError | None = None
    last: httpx.Response | None = None
    for attempt in range(attempts):
        retry_after: float | None = None
        status: int | None = None
        try:
            r = await client.post(url, headers=headers, json=json)
        except RETRYABLE_TRANSPORT_ERRORS as exc:
            last_exc = exc
            last = None
        else:
            last_exc = None
            last = r
            status = r.status_code
            if not is_retryable_status(status):
                return r
            retry_after = parse_retry_after(r.headers.get("retry-after"))
        if attempt >= attempts - 1:
            break
        delay = compute_backoff_delay(attempt, retry_after_s=retry_after, rand=rand)
        if (time.monotonic() - started) + delay > max_elapsed_s:
            break
        _log_retry(attempt, delay, status=status, exc=last_exc)
        await sleep(delay)
    if last is not None:
        return last
    assert last_exc is not None
    raise last_exc


async def _raise_http_error(resp: httpx.Response, err_prefix: str) -> NoReturn:
    err_body = await resp.aread()
    await resp.aclose()
    msg = f"{err_prefix} error {resp.status_code}: {err_body[:500]!r}"
    raise OSError(msg)


async def _prepend_chunk(first: bytes | None, rest: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    if first is not None:
        yield first
    async for chunk in rest:
        yield chunk


async def httpx_stream_bytes_with_retries(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    json: Any,
    max_retries: int = DEFAULT_MAX_ATTEMPTS,
    max_elapsed_s: float = DEFAULT_MAX_ELAPSED_S,
    err_prefix: str = "HTTP",
    rand: Callable[[], float] = random.random,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
) -> tuple[httpx.Response, AsyncIterator[bytes]]:
    """Open a streaming POST, retrying until the FIRST body chunk is secured.

    The retry window covers connection setup, retryable HTTP statuses, and
    transport errors while acquiring the first body chunk. Once any chunk
    has been handed to the caller, NO retry is possible: SSE events already
    yielded downstream may have had side effects (partial text shown to a
    user, usage telemetry emitted), so replaying the request would duplicate
    them. Later failures surface from the returned iterator instead.

    A non-retryable (or still-failing final) HTTP status raises ``OSError``
    carrying the response body, prefixed with ``err_prefix``. On success the
    caller owns closing the returned response (``await resp.aclose()``).
    """
    started = time.monotonic()
    attempts = max(max_retries, 1)
    last_exc: httpx.TransportError | None = None
    resp: httpx.Response | None = None
    for attempt in range(attempts):
        retry_after: float | None = None
        status: int | None = None
        try:
            request = client.build_request("POST", url, headers=headers, json=json)
            resp = await client.send(request, stream=True)
        except RETRYABLE_TRANSPORT_ERRORS as exc:
            last_exc = exc
            resp = None
        else:
            last_exc = None
            status = resp.status_code
            if is_retryable_status(status):
                retry_after = parse_retry_after(resp.headers.get("retry-after"))
            elif status >= 400:
                await _raise_http_error(resp, err_prefix)
            else:
                body = resp.aiter_bytes()
                try:
                    first = await anext(body, None)
                except RETRYABLE_TRANSPORT_ERRORS as exc:
                    last_exc = exc
                    await resp.aclose()
                    resp = None
                else:
                    return resp, _prepend_chunk(first, body)
        if attempt >= attempts - 1:
            break
        delay = compute_backoff_delay(attempt, retry_after_s=retry_after, rand=rand)
        if (time.monotonic() - started) + delay > max_elapsed_s:
            break
        if resp is not None:
            await resp.aclose()
            resp = None
        _log_retry(attempt, delay, status=status, exc=last_exc)
        await sleep(delay)
    if resp is not None:
        await _raise_http_error(resp, err_prefix)
    assert last_exc is not None
    raise last_exc
