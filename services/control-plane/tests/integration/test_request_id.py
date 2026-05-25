"""``X-Request-ID`` round-trip: generated, preserved, or replaced on invalid input."""

from __future__ import annotations

import uuid

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine

from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.main import app

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


@pytest.mark.asyncio
async def test_missing_header_generates_uuid(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    clear_settings_cache()
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/healthz")
        assert resp.status_code == 200
        echoed = resp.headers["X-Request-ID"]
        assert _is_uuid(echoed)
    finally:
        clear_settings_cache()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_valid_header_is_preserved(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    clear_settings_cache()
    clear_engine_cache()
    incoming = str(uuid.uuid4())
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/healthz", headers={"X-Request-ID": incoming})
        assert resp.status_code == 200
        assert resp.headers["X-Request-ID"] == incoming
    finally:
        clear_settings_cache()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_invalid_header_is_replaced(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    clear_settings_cache()
    clear_engine_cache()
    bogus = "not-a-uuid-at-all"
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/healthz", headers={"X-Request-ID": bogus})
        assert resp.status_code == 200
        echoed = resp.headers["X-Request-ID"]
        assert echoed != bogus
        assert _is_uuid(echoed)
    finally:
        clear_settings_cache()
        clear_engine_cache()
