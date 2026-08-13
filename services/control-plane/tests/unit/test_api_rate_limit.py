"""Unit tests for the inbound API rate limiter (bucket math, keying, defaults)."""

from __future__ import annotations

from collections.abc import AsyncIterator

import fakeredis.aioredis
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from control_plane.config.settings import clear_settings_cache
from control_plane.infra.rate_limit import (
    MemoryTokenBucketLimiter,
    RateLimitMiddleware,
    derive_rate_limit_key,
    is_rate_limit_exempt,
    redis_fixed_window_check,
    reset_rate_limiter_state,
)

# --- bucket math -------------------------------------------------------------


class TestMemoryTokenBucket:
    def test_burst_up_to_capacity_then_denied(self) -> None:
        limiter = MemoryTokenBucketLimiter()
        for _ in range(5):
            assert limiter.check("k", capacity=5.0, refill_per_second=1.0, now=100.0).allowed
        assert not limiter.check("k", capacity=5.0, refill_per_second=1.0, now=100.0).allowed

    def test_exhaustion_reports_retry_after(self) -> None:
        limiter = MemoryTokenBucketLimiter()
        assert limiter.check("k", capacity=1.0, refill_per_second=0.5, now=0.0).allowed
        decision = limiter.check("k", capacity=1.0, refill_per_second=0.5, now=0.0)
        assert not decision.allowed
        # 1 token at 0.5 tokens/s => 2 seconds until the next request fits.
        assert decision.retry_after_seconds == pytest.approx(2.0)

    def test_refill_restores_tokens_over_time(self) -> None:
        limiter = MemoryTokenBucketLimiter()
        for _ in range(2):
            assert limiter.check("k", capacity=2.0, refill_per_second=1.0, now=10.0).allowed
        assert not limiter.check("k", capacity=2.0, refill_per_second=1.0, now=10.0).allowed
        # One second later exactly one token has refilled.
        assert limiter.check("k", capacity=2.0, refill_per_second=1.0, now=11.0).allowed
        assert not limiter.check("k", capacity=2.0, refill_per_second=1.0, now=11.0).allowed

    def test_refill_never_exceeds_capacity(self) -> None:
        limiter = MemoryTokenBucketLimiter()
        assert limiter.check("k", capacity=2.0, refill_per_second=1.0, now=0.0).allowed
        # A long idle period refills to capacity (2), not capacity + elapsed.
        for _ in range(2):
            assert limiter.check("k", capacity=2.0, refill_per_second=1.0, now=1000.0).allowed
        assert not limiter.check("k", capacity=2.0, refill_per_second=1.0, now=1000.0).allowed

    def test_keys_are_independent(self) -> None:
        limiter = MemoryTokenBucketLimiter()
        assert limiter.check("a", capacity=1.0, refill_per_second=1.0, now=0.0).allowed
        assert not limiter.check("a", capacity=1.0, refill_per_second=1.0, now=0.0).allowed
        assert limiter.check("b", capacity=1.0, refill_per_second=1.0, now=0.0).allowed


# --- key derivation ----------------------------------------------------------


class TestKeyDerivation:
    def test_authorization_header_wins_and_is_hashed(self) -> None:
        key = derive_rate_limit_key(
            authorization="Bearer secret-token",
            session_cookie="cookie-value",
            forwarded_for="1.2.3.4",
            client_host="5.6.7.8",
        )
        assert key.startswith("auth:")
        assert "secret-token" not in key

    def test_same_token_same_key_different_token_different_key(self) -> None:
        common = {"session_cookie": None, "forwarded_for": None, "client_host": None}
        a1 = derive_rate_limit_key(authorization="Bearer aaa", **common)
        a2 = derive_rate_limit_key(authorization="Bearer aaa", **common)
        b = derive_rate_limit_key(authorization="Bearer bbb", **common)
        assert a1 == a2
        assert a1 != b

    def test_cookie_fallback_is_hashed(self) -> None:
        key = derive_rate_limit_key(
            authorization=None,
            session_cookie="opaque-session",
            forwarded_for="1.2.3.4",
            client_host="5.6.7.8",
        )
        assert key.startswith("cookie:")
        assert "opaque-session" not in key

    def test_forwarded_for_uses_first_hop(self) -> None:
        key = derive_rate_limit_key(
            authorization=None,
            session_cookie=None,
            forwarded_for="203.0.113.9, 10.0.0.1, 10.0.0.2",
            client_host="5.6.7.8",
        )
        assert key == "ip:203.0.113.9"

    def test_client_host_last_resort(self) -> None:
        key = derive_rate_limit_key(
            authorization=None,
            session_cookie=None,
            forwarded_for=None,
            client_host="5.6.7.8",
        )
        assert key == "ip:5.6.7.8"

    def test_nothing_resolvable_is_still_a_key(self) -> None:
        key = derive_rate_limit_key(
            authorization=None,
            session_cookie=None,
            forwarded_for="  ",
            client_host=None,
        )
        assert key == "ip:unknown"


# --- exemptions --------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/healthz", "/health", "/readyz", "/metrics", "/internal/v1/tenants", "/internal/v1/metrics"],
)
def test_exempt_paths(path: str) -> None:
    assert is_rate_limit_exempt(path)


@pytest.mark.parametrize(
    "path",
    ["/integrations/catalog", "/auth/refresh", "/platform/accounts", "/scim/v2/Users"],
)
def test_public_paths_not_exempt(path: str) -> None:
    assert not is_rate_limit_exempt(path)


# --- Redis fixed-window backend (fakeredis, no server needed) ----------------


@pytest.fixture()
async def fake_redis() -> AsyncIterator[fakeredis.aioredis.FakeRedis]:
    client = fakeredis.aioredis.FakeRedis(decode_responses=True)
    try:
        yield client
    finally:
        await client.aclose()


async def test_redis_window_allows_budget_then_denies(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    for _ in range(3):
        assert (await redis_fixed_window_check(fake_redis, "k", budget=3)).allowed
    decision = await redis_fixed_window_check(fake_redis, "k", budget=3)
    assert not decision.allowed
    assert 0.0 < decision.retry_after_seconds <= 60.0


async def test_redis_window_keys_are_independent(
    fake_redis: fakeredis.aioredis.FakeRedis,
) -> None:
    assert (await redis_fixed_window_check(fake_redis, "a", budget=1)).allowed
    assert not (await redis_fixed_window_check(fake_redis, "a", budget=1)).allowed
    assert (await redis_fixed_window_check(fake_redis, "b", budget=1)).allowed


# --- middleware default: disabled unless the env opts in ---------------------


def _mini_app() -> FastAPI:
    mini = FastAPI()
    mini.add_middleware(RateLimitMiddleware)

    @mini.get("/widgets")
    async def widgets() -> dict[str, bool]:
        return {"ok": True}

    @mini.get("/healthz")
    async def healthz() -> dict[str, bool]:
        return {"ok": True}

    return mini


async def test_middleware_pass_through_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEPLOYAI_API_RATE_LIMIT_PER_MINUTE", raising=False)
    clear_settings_cache()
    try:
        transport = ASGITransport(app=_mini_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for _ in range(25):
                assert (await client.get("/widgets")).status_code == 200
    finally:
        clear_settings_cache()


async def test_middleware_enforces_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_API_RATE_LIMIT_PER_MINUTE", "2")
    monkeypatch.delenv("DEPLOYAI_API_RATE_LIMIT_BURST", raising=False)
    monkeypatch.delenv("DEPLOYAI_REDIS_URL", raising=False)
    clear_settings_cache()
    reset_rate_limiter_state()
    try:
        transport = ASGITransport(app=_mini_app())
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            assert (await client.get("/widgets")).status_code == 200
            assert (await client.get("/widgets")).status_code == 200
            resp = await client.get("/widgets")
            assert resp.status_code == 429
            assert resp.json() == {"error": "rate_limited"}
            assert int(resp.headers["Retry-After"]) >= 1
            # Exempt paths never consume or hit the bucket.
            for _ in range(5):
                assert (await client.get("/healthz")).status_code == 200
    finally:
        clear_settings_cache()
        reset_rate_limiter_state()
