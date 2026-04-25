from __future__ import annotations

import hashlib
import time
from collections.abc import Callable
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


def httpx_post_with_retries(
    client: httpx.Client,
    url: str,
    *,
    headers: dict[str, str],
    json: Any,
    max_retries: int = 4,
) -> httpx.Response:
    """5xx and 429 → exponential backoff; other errors return immediately."""
    delay = 0.15
    last: httpx.Response | None = None
    for attempt in range(max_retries):
        r = client.post(url, headers=headers, json=json)
        last = r
        if r.status_code < 500 and r.status_code != 429:
            return r
        if r.status_code == 429 or r.status_code >= 500:
            if attempt < max_retries - 1:
                time.sleep(delay * (2**attempt))
                continue
        return r
    assert last is not None
    return last
