"""Phase D D1.c: ``/healthz`` + ``/readyz`` + ``/metrics`` end-to-end smoke."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine

from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.main import app

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_healthz_returns_ok(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    clear_settings_cache()
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/healthz")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"
    finally:
        clear_settings_cache()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_readyz_returns_ready_when_db_up(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    clear_settings_cache()
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/readyz")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ready"}
    finally:
        clear_settings_cache()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_metrics_returns_prometheus_text(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    clear_settings_cache()
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/metrics")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/plain")
        body = resp.text
        assert "# HELP" in body
    finally:
        clear_settings_cache()
        clear_engine_cache()
