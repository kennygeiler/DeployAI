"""Rate-limit middleware against the real app: 429 + Retry-After, exemptions, Redis backend."""

from __future__ import annotations

from collections.abc import Generator

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine

import control_plane.infra.rate_limit as rate_limit_mod
from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.infra.rate_limit import reset_rate_limiter_state
from control_plane.main import app

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration

# Unauthenticated public GET — the limiter must fire before any auth dependency.
_PUBLIC_PATH = "/integrations/catalog"


@pytest.fixture()
def rate_limited_env(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> Generator[None]:
    """limit=2/min via env, in-memory backend, caches cleared on both sides."""
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_API_RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.delenv("DEPLOYAI_API_RATE_LIMIT_BURST", raising=False)
    monkeypatch.delenv("DEPLOYAI_REDIS_URL", raising=False)
    clear_settings_cache()
    clear_engine_cache()
    reset_rate_limiter_state()
    yield
    clear_settings_cache()
    clear_engine_cache()
    reset_rate_limiter_state()


async def test_third_request_gets_429_with_retry_after(rate_limited_env: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get(_PUBLIC_PATH)).status_code == 200
        assert (await client.get(_PUBLIC_PATH)).status_code == 200
        resp = await client.get(_PUBLIC_PATH)
    assert resp.status_code == 429
    assert resp.json() == {"error": "rate_limited"}
    retry_after = int(resp.headers["Retry-After"])
    assert 1 <= retry_after <= 60


async def test_distinct_principals_get_separate_buckets(rate_limited_env: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for _ in range(2):
            resp = await client.get(_PUBLIC_PATH, headers={"Authorization": "Bearer principal-a"})
            assert resp.status_code == 200
        # principal-a is exhausted; principal-b still has a full bucket.
        resp = await client.get(_PUBLIC_PATH, headers={"Authorization": "Bearer principal-a"})
        assert resp.status_code == 429
        resp = await client.get(_PUBLIC_PATH, headers={"Authorization": "Bearer principal-b"})
        assert resp.status_code == 200


async def test_excluded_paths_never_429(rate_limited_env: None) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        for path in ("/healthz", "/health", "/metrics"):
            for _ in range(5):
                resp = await client.get(path)
                assert resp.status_code == 200, path
        # Readiness may 200 or 503 depending on DB reachability — never 429.
        for _ in range(5):
            assert (await client.get("/readyz")).status_code != 429
        # /internal/* is internal-key gated, not rate limited: 401, never 429.
        for _ in range(5):
            resp = await client.get("/internal/v1/metrics")
            assert resp.status_code == 401


async def test_redis_backend_via_fakeredis(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_API_RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.delenv("DEPLOYAI_API_RATE_LIMIT_BURST", raising=False)
    monkeypatch.setenv("DEPLOYAI_REDIS_URL", "redis://rate-limit-test:6379/0")
    fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(rate_limit_mod, "get_async_redis", lambda: fake)
    clear_settings_cache()
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get(_PUBLIC_PATH)).status_code == 200
            assert (await client.get(_PUBLIC_PATH)).status_code == 200
            resp = await client.get(_PUBLIC_PATH)
        assert resp.status_code == 429
        assert resp.json() == {"error": "rate_limited"}
        assert 1 <= int(resp.headers["Retry-After"]) <= 60
    finally:
        await fake.aclose()
        clear_settings_cache()
        clear_engine_cache()
