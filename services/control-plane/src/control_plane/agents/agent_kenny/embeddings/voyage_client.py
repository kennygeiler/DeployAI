"""Voyage-3 embeddings client (v2 Phase 5.5 Wave B, scope-v2 §10.2).

Thin async wrapper over Voyage AI's ``POST /v1/embeddings`` endpoint. Used by
``control_plane.workers.embedder`` to vectorize curated text rows (ledger
events, matrix nodes, oracle chat turns, matrix insights) into the
``embedding vector(1024)`` columns added by Wave A's migration.

Local-dev fallback
------------------
If ``VOYAGE_API_KEY`` is unset, ``embed`` logs a warning **once per process**
and returns deterministic zero-vectors of the right shape. This keeps the
worker green on dev boxes without Voyage credentials — vector search degrades
to "everything is equally similar" until a real key is supplied, which is the
right failure mode given embeddings are the fallback retrieval path
(``docs/agent-kenny/ethos.md``), not the hot path.

Reliability
-----------
- 30-second timeout per call (Voyage typically responds < 2s for a 50-row batch).
- One retry with 1s backoff on 5xx. 4xx surfaces immediately because they
  indicate a malformed payload — retrying would just burn quota.
- Network exceptions also retry once; persistent failure raises ``VoyageError``
  so the worker can mark the affected ``embedding_jobs`` row failed.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

_log = logging.getLogger(__name__)

VOYAGE_URL = "https://api.voyageai.com/v1/embeddings"
VOYAGE_MODEL = "voyage-3"
VOYAGE_DIM = 1024
VOYAGE_TIMEOUT_S = 30.0
VOYAGE_RETRY_BACKOFF_S = 1.0

_API_KEY_ENV = "VOYAGE_API_KEY"
_warned_missing_key = False


class VoyageError(RuntimeError):
    """Raised when the Voyage API returns an unrecoverable error."""


def _resolve_api_key() -> str:
    return (os.environ.get(_API_KEY_ENV) or "").strip()


def _warn_missing_key_once() -> None:
    global _warned_missing_key
    if _warned_missing_key:
        return
    _warned_missing_key = True
    _log.warning(
        "%s is not set; embedder will emit zero-vectors. Vector search will "
        "behave as 'all rows equally similar' until a key is supplied. This "
        "is the documented local-dev fallback (scope-v2 §10.2).",
        _API_KEY_ENV,
    )


class VoyageEmbedder:
    """Async Voyage-3 batch embedder.

    Construct once per worker tick (or once per process — it's stateless apart
    from the optional injected httpx client used by tests).
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = VOYAGE_MODEL,
        timeout_s: float = VOYAGE_TIMEOUT_S,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        # Resolve the key lazily on each ``embed`` call, not at construction:
        # the local-dev fallback log line should fire when the worker actually
        # tries to embed, not when the CLI imports the class at startup.
        self._explicit_key = (api_key or "").strip() or None
        self._model = model
        self._timeout_s = timeout_s
        self._client = client

    def _headers(self, key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    async def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed ``texts`` → list of 1024-dim vectors, one per input.

        Returns zero-vectors when ``VOYAGE_API_KEY`` is unset (local-dev
        fallback). Raises :class:`VoyageError` on persistent API failure so
        the worker can mark the row failed and move on.
        """
        if not texts:
            return []

        key = self._explicit_key or _resolve_api_key()
        if not key:
            _warn_missing_key_once()
            return [[0.0] * VOYAGE_DIM for _ in texts]

        body: dict[str, Any] = {"input": texts, "model": self._model}
        if self._client is not None:
            response = await self._post_with_retries(self._client, key, body)
        else:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                response = await self._post_with_retries(client, key, body)
        return self._parse_response(response, expected=len(texts))

    async def _post_with_retries(
        self,
        client: httpx.AsyncClient,
        key: str,
        body: dict[str, Any],
    ) -> httpx.Response:
        """Single retry on 5xx / network error; 4xx returns immediately."""
        import asyncio

        last_exc: Exception | None = None
        for attempt in range(2):
            try:
                response = await client.post(
                    VOYAGE_URL,
                    headers=self._headers(key),
                    json=body,
                    timeout=self._timeout_s,
                )
            except (httpx.RequestError, httpx.TimeoutException) as exc:
                last_exc = exc
                if attempt == 0:
                    await asyncio.sleep(VOYAGE_RETRY_BACKOFF_S)
                    continue
                msg = f"Voyage request failed after retry: {exc}"
                raise VoyageError(msg) from exc
            if response.status_code < 500:
                return response
            if attempt == 0:
                await asyncio.sleep(VOYAGE_RETRY_BACKOFF_S)
                continue
            return response
        # Unreachable — loop body always returns or raises by attempt == 1.
        if last_exc is not None:  # pragma: no cover
            raise VoyageError(str(last_exc)) from last_exc
        msg = "Voyage retry loop exited without a response"  # pragma: no cover
        raise VoyageError(msg)  # pragma: no cover

    def _parse_response(self, response: httpx.Response, *, expected: int) -> list[list[float]]:
        if response.status_code >= 400:
            msg = f"Voyage error {response.status_code}: {response.text[:500]}"
            raise VoyageError(msg)
        try:
            payload = response.json()
        except ValueError as exc:
            msg = f"Voyage response was not JSON: {exc}"
            raise VoyageError(msg) from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            msg = f"Voyage response missing .data: {payload!r}"
            raise VoyageError(msg)
        if len(data) != expected:
            msg = f"Voyage returned {len(data)} embeddings for {expected} inputs"
            raise VoyageError(msg)
        vectors: list[list[float]] = []
        for entry in data:
            if not isinstance(entry, dict):
                msg = f"Voyage .data entry not a dict: {entry!r}"
                raise VoyageError(msg)
            embedding = entry.get("embedding")
            if not isinstance(embedding, list) or len(embedding) != VOYAGE_DIM:
                msg = f"Voyage .embedding wrong shape: dim={len(embedding) if isinstance(embedding, list) else 'n/a'}"
                raise VoyageError(msg)
            vectors.append([float(x) for x in embedding])
        return vectors


__all__ = ["VOYAGE_DIM", "VOYAGE_MODEL", "VoyageEmbedder", "VoyageError"]
