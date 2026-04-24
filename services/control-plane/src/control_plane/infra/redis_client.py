"""Process-wide async Redis (Story 2-4)."""

from __future__ import annotations

import redis.asyncio as redis

from control_plane.config.settings import get_settings

_client: redis.Redis | None = None


def get_async_redis() -> redis.Redis:
    global _client
    if _client is None:
        s = get_settings()
        if s.redis_url.startswith("rediss://"):
            _client = redis.from_url(
                s.redis_url,
                decode_responses=True,
                ssl_certfile=s.redis_ssl_certfile,
                ssl_keyfile=s.redis_ssl_keyfile,
                ssl_ca_certs=s.redis_ssl_ca_certs,
            )
        else:
            _client = redis.from_url(s.redis_url, decode_responses=True)
    return _client


async def close_async_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def clear_redis_client() -> None:
    global _client
    _client = None
