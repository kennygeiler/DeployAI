"""Unit tests for the Voyage-3 embedding client (Phase 5.5 Wave B)."""

from __future__ import annotations

import logging

import httpx
import pytest

from control_plane.agents.agent_kenny.embeddings import voyage_client
from control_plane.agents.agent_kenny.embeddings.voyage_client import (
    VOYAGE_DIM,
    VOYAGE_MODEL,
    VOYAGE_URL,
    VoyageEmbedder,
    VoyageError,
)


@pytest.fixture(autouse=True)
def _reset_warn_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets a fresh "have we warned yet" state."""
    monkeypatch.setattr(voyage_client, "_warned_missing_key", False)


def _ok_payload(n: int, *, dim: int = VOYAGE_DIM) -> dict[str, object]:
    return {
        "data": [{"embedding": [0.1] * dim, "index": i} for i in range(n)],
        "model": VOYAGE_MODEL,
    }


@pytest.mark.asyncio
async def test_embed_happy_path_returns_vectors(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("Authorization")
        captured["body"] = request.content
        return httpx.Response(200, json=_ok_payload(3))

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key-xyz")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = VoyageEmbedder(client=client)
        vectors = await embedder.embed(["a", "b", "c"])

    assert captured["url"] == VOYAGE_URL
    assert captured["auth"] == "Bearer test-key-xyz"
    assert len(vectors) == 3
    assert all(len(v) == VOYAGE_DIM for v in vectors)


@pytest.mark.asyncio
async def test_embed_5xx_retries_once_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """First call returns 503, second call returns 200 → vectors come back."""
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] == 1:
            return httpx.Response(503, json={"error": "upstream"})
        return httpx.Response(200, json=_ok_payload(2))

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    # Patch the backoff to 0 so the test stays fast.
    monkeypatch.setattr(voyage_client, "VOYAGE_RETRY_BACKOFF_S", 0.0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = VoyageEmbedder(client=client)
        vectors = await embedder.embed(["x", "y"])

    assert counter["n"] == 2
    assert len(vectors) == 2


@pytest.mark.asyncio
async def test_embed_5xx_twice_raises_voyage_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both calls 5xx → VoyageError surfaces so the worker marks the job failed."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(voyage_client, "VOYAGE_RETRY_BACKOFF_S", 0.0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = VoyageEmbedder(client=client)
        with pytest.raises(VoyageError):
            await embedder.embed(["x"])


@pytest.mark.asyncio
async def test_embed_4xx_no_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """4xx should not be retried — retrying a malformed payload just burns quota."""
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(400, text="bad request")

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(voyage_client, "VOYAGE_RETRY_BACKOFF_S", 0.0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = VoyageEmbedder(client=client)
        with pytest.raises(VoyageError):
            await embedder.embed(["x"])

    assert counter["n"] == 1


@pytest.mark.asyncio
async def test_embed_missing_key_emits_zero_vectors_with_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unset key → zero-vectors + one warning. Local-dev fallback path."""
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    embedder = VoyageEmbedder()
    with caplog.at_level(logging.WARNING, logger=voyage_client.__name__):
        vectors = await embedder.embed(["hello", "world"])

    assert len(vectors) == 2
    assert all(len(v) == VOYAGE_DIM for v in vectors)
    assert all(all(component == 0.0 for component in v) for v in vectors)
    assert any("VOYAGE_API_KEY" in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
async def test_embed_missing_key_warns_only_once(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)

    embedder = VoyageEmbedder()
    with caplog.at_level(logging.WARNING, logger=voyage_client.__name__):
        await embedder.embed(["a"])
        await embedder.embed(["b"])

    warnings = [r for r in caplog.records if "VOYAGE_API_KEY" in r.getMessage()]
    assert len(warnings) == 1


@pytest.mark.asyncio
async def test_embed_empty_input_short_circuits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Empty list → empty list, no network round-trip."""
    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover — should never fire
        raise AssertionError("network call should not happen for empty input")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = VoyageEmbedder(client=client)
        assert await embedder.embed([]) == []


@pytest.mark.asyncio
async def test_embed_rejects_wrong_dim_response(monkeypatch: pytest.MonkeyPatch) -> None:
    """If Voyage returns a vector with wrong dimensionality we refuse to write garbage."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"embedding": [0.1] * 512, "index": 0}], "model": VOYAGE_MODEL},
        )

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = VoyageEmbedder(client=client)
        with pytest.raises(VoyageError, match="wrong shape"):
            await embedder.embed(["x"])


@pytest.mark.asyncio
async def test_embed_rejects_count_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    """Voyage returned 2 vectors for 3 inputs → refuse, don't guess."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_ok_payload(2))

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = VoyageEmbedder(client=client)
        with pytest.raises(VoyageError, match="returned 2"):
            await embedder.embed(["x", "y", "z"])
