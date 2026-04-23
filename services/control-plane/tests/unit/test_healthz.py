"""Smoke tests for the `/healthz` (k8s convention) and `/health` (Story 1.7
docker-compose AC) endpoints. Both are aliases returning the same body.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from control_plane.main import app


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/healthz", "/health"])
async def test_health_endpoints_return_ok(path: str) -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "control-plane"
    assert "version" in body
