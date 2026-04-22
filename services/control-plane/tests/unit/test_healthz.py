"""Smoke test for the /healthz endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from control_plane.main import app


@pytest.mark.asyncio
async def test_healthz_returns_ok() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
