"""Microsoft Graph request helper with 429 / Retry-After + token-bucket throttling (Epic 3 Story 3-7, NFR19)."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

_LOG = logging.getLogger(__name__)

_MAX_429 = 6


class GraphTokenBucket:
    """Token bucket for Graph requests (Story 3-7, default 1000 r/s in settings)."""

    def __init__(self, *, rate_per_sec: float) -> None:
        self._rate = max(0.1, float(rate_per_sec))
        self._tokens = self._rate
        self._last = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last
            self._last = now
            self._tokens = min(self._rate, self._tokens + elapsed * self._rate)
            if self._tokens < 1.0:
                need = 1.0 - self._tokens
                wait = need / self._rate
                self._tokens = 0.0
                await asyncio.sleep(wait)
            else:
                self._tokens -= 1.0


def _retry_after_sec(resp: httpx.Response) -> float:
    h = (resp.headers.get("Retry-After") or "").strip()
    if h.isdecimal():
        return float(int(h, 10))
    try:
        return float(h)
    except ValueError:
        return 0.0


async def m365_graph_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    auth: str,
    params: Mapping[str, str] | None,
    bucket: GraphTokenBucket,
    timeout: float = 60.0,  # noqa: ASYNC109 — httpx client timeout, not asyncio timeout
    odata_max_page: str | None = "100",
) -> httpx.Response:
    """Delegated Graph GET (M365 mail / Teams) with 429 + token-bucket; ``odata_max_page=None`` omits ``Prefer``."""
    headers: dict[str, str] = {"Authorization": f"Bearer {auth}"}
    if odata_max_page is not None and odata_max_page.strip() != "":
        headers["Prefer"] = f"odata.maxpagesize={odata_max_page}"
    return await graph_request(
        client,
        "GET",
        str(url),
        bucket=bucket,
        reauthorize=None,
        headers=headers,
        params=params,
        timeout=timeout,
    )


async def graph_request(
    client: httpx.AsyncClient,
    method: str,
    url: str,
    *,
    bucket: GraphTokenBucket | None,
    reauthorize: Callable[[], Awaitable[None]] | None = None,
    **kwargs: Any,
) -> httpx.Response:
    """GET/POST/... Graph; honors ``Retry-After`` on 429, optional throttling, one 401 reauth pass."""
    for attempt in range(_MAX_429 + 1):
        if bucket is not None:
            await bucket.acquire()
        r = await client.request(method, url, **kwargs)
        if r.status_code == 401 and reauthorize is not None and attempt == 0:
            await reauthorize()
            r = await client.request(method, url, **kwargs)
        if r.status_code != 429:
            if r.is_server_error and r.status_code >= 500:
                _LOG.warning("graph 5xx: %s %s", r.status_code, (url or "")[:120])
            return r
        if attempt >= _MAX_429:
            return r
        ra = _retry_after_sec(r)
        delay = max(0.0, min(300.0, ra if ra > 0 else 2.0 ** min(8, attempt)))
        _LOG.info("graph 429, sleeping %.1fs (attempt %s)", delay, attempt + 1)
        await asyncio.sleep(delay)
    return r
