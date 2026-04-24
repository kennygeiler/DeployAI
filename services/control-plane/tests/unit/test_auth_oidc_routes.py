"""ASGI tests for OIDC route wiring (no IdP)."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from control_plane.config.settings import clear_settings_cache
from control_plane.main import app


@pytest.mark.asyncio
async def test_oidc_login_503_without_config() -> None:
    clear_settings_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/auth/oidc/login", follow_redirects=False)
        assert r.status_code == 503
    finally:
        clear_settings_cache()
