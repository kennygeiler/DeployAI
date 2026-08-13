"""Unit tests for the Voyage-3 embedding client (Phase 5.5 Wave B)."""

from __future__ import annotations

import httpx
import pytest

from control_plane.agents.agent_kenny.embeddings import voyage_client
from control_plane.agents.agent_kenny.embeddings.voyage_client import (
    VOYAGE_DIM,
    VOYAGE_MODEL,
    VOYAGE_URL,
    VoyageCircuitOpen,
    VoyageEmbedder,
    VoyageError,
    reset_voyage_breaker_for_tests,
)
from control_plane.infra.circuit_breaker import CircuitBreaker


@pytest.fixture(autouse=True)
def _reset_warn_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """Each test gets a fresh "have we warned yet" state + a clean env.

    The CI runner may have ``VOYAGE_API_KEY`` populated via compose ``.env``;
    the missing-key tests need a guaranteed-empty env. Tests that need the
    key set re-monkeypatch. The shared circuit breaker is also reset so no
    test inherits tripped state from an earlier one.
    """
    monkeypatch.setattr(voyage_client, "_warned_missing_key", False)
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    reset_voyage_breaker_for_tests()


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
async def test_embed_missing_key_emits_zero_vectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset key → zero-vectors fallback (local-dev path)."""
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setattr(voyage_client, "_resolve_api_key", lambda: "")

    embedder = VoyageEmbedder()
    vectors = await embedder.embed(["hello", "world"])

    assert len(vectors) == 2
    assert all(len(v) == VOYAGE_DIM for v in vectors)
    assert all(all(component == 0.0 for component in v) for v in vectors)


@pytest.mark.asyncio
async def test_embed_missing_key_returns_zero_vectors_each_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Repeated calls with missing key all return zero-vectors."""
    monkeypatch.delenv("VOYAGE_API_KEY", raising=False)
    monkeypatch.setattr(voyage_client, "_resolve_api_key", lambda: "")

    embedder = VoyageEmbedder()
    first = await embedder.embed(["a"])
    second = await embedder.embed(["b"])

    assert len(first) == 1 and all(c == 0.0 for c in first[0])
    assert len(second) == 1 and all(c == 0.0 for c in second[0])


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
async def test_circuit_open_raises_voyage_error_without_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Tripped breaker → VoyageCircuitOpen (a VoyageError) and zero HTTP attempts,
    so callers degrade exactly as they do for a live Voyage outage."""
    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        return httpx.Response(503, text="down")

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(voyage_client, "VOYAGE_RETRY_BACKOFF_S", 0.0)
    breaker = CircuitBreaker("voyage-t-open", failure_threshold=1, cooldown_s=30.0)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = VoyageEmbedder(client=client, breaker=breaker)
        with pytest.raises(VoyageError):
            await embedder.embed(["x"])  # trips: one embed = one breaker failure
        attempts_before = counter["n"]
        with pytest.raises(VoyageCircuitOpen) as excinfo:
            await embedder.embed(["x"])

    assert counter["n"] == attempts_before, "open circuit must not touch the network"
    assert isinstance(excinfo.value, VoyageError)


@pytest.mark.asyncio
async def test_circuit_probe_success_closes_and_embeds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Clock:
        now = 0.0

        def __call__(self) -> float:
            return _Clock.now

    counter = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        counter["n"] += 1
        if counter["n"] <= 2:  # first embed: initial attempt + one retry, both 503
            return httpx.Response(503, text="down")
        return httpx.Response(200, json=_ok_payload(1))

    monkeypatch.setenv("VOYAGE_API_KEY", "test-key")
    monkeypatch.setattr(voyage_client, "VOYAGE_RETRY_BACKOFF_S", 0.0)
    breaker = CircuitBreaker("voyage-t-probe", failure_threshold=1, cooldown_s=30.0, clock=_Clock())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        embedder = VoyageEmbedder(client=client, breaker=breaker)
        with pytest.raises(VoyageError):
            await embedder.embed(["x"])
        with pytest.raises(VoyageCircuitOpen):
            await embedder.embed(["x"])
        _Clock.now = 31.0
        vectors = await embedder.embed(["x"])  # the probe — succeeds, closes

    assert len(vectors) == 1
    assert len(vectors[0]) == VOYAGE_DIM


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
