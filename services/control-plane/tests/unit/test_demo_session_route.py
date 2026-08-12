"""ASGI tests for POST /internal/v1/demo/session (Wave 4S guest demo access).

No Redis: ``issue_tokens`` is monkeypatched where enabled-path minting is
asserted; the disabled/misconfigured paths never reach it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from httpx import ASGITransport, AsyncClient

import control_plane.api.routes.demo_session_internal as demo_mod
from control_plane.auth.session_service import SessionPair
from control_plane.config.settings import clear_settings_cache
from control_plane.main import app

DEMO_TENANT = "33333333-3333-3333-3333-333333333333"
DEMO_USER = "44444444-4444-4444-4444-444444444444"
INTERNAL_KEY = "demo-int-key"


def _client() -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://t")


def _configure(monkeypatch: pytest.MonkeyPatch, **overrides: str) -> None:
    env = {
        "DEPLOYAI_INTERNAL_API_KEY": INTERNAL_KEY,
        "DEPLOYAI_DEMO_GUEST_ENABLED": "1",
        "DEPLOYAI_DEMO_TENANT_ID": DEMO_TENANT,
        "DEPLOYAI_DEMO_USER_ID": DEMO_USER,
        **overrides,
    }
    for k, v in env.items():
        if v == "":
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, v)
    clear_settings_cache()


@pytest.fixture(autouse=True)
def _settings_cache() -> Iterator[None]:
    clear_settings_cache()
    yield
    clear_settings_cache()


@pytest.mark.asyncio
async def test_404_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, DEPLOYAI_DEMO_GUEST_ENABLED="")
    async with _client() as c:
        r = await c.post("/internal/v1/demo/session", headers={"X-DeployAI-Internal-Key": INTERNAL_KEY})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_404_when_enabled_but_tenant_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, DEPLOYAI_DEMO_TENANT_ID="")
    async with _client() as c:
        r = await c.post("/internal/v1/demo/session", headers={"X-DeployAI-Internal-Key": INTERNAL_KEY})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_404_when_demo_ids_malformed(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, DEPLOYAI_DEMO_TENANT_ID="not-a-uuid")
    async with _client() as c:
        r = await c.post("/internal/v1/demo/session", headers={"X-DeployAI-Internal-Key": INTERNAL_KEY})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_401_without_internal_key_even_when_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    async with _client() as c:
        r = await c.post("/internal/v1/demo/session")
    assert r.status_code == 401


def _capture_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> list[tuple[uuid.UUID, uuid.UUID, list[str], int | None]]:
    """Monkeypatch issue_tokens; echo the threaded TTL back as expires_in."""
    calls: list[tuple[uuid.UUID, uuid.UUID, list[str], int | None]] = []

    async def fake_issue(
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        roles: list[str],
        *,
        access_ttl_seconds: int | None = None,
    ) -> SessionPair:
        calls.append((tenant_id, user_id, roles, access_ttl_seconds))
        return SessionPair(
            access_token="demo-access-jwt",
            refresh_jti="demo-refresh",
            expires_in=access_ttl_seconds if access_ttl_seconds is not None else 900,
        )

    monkeypatch.setattr(demo_mod, "issue_tokens", fake_issue)
    return calls


@pytest.mark.asyncio
async def test_mints_demo_guest_session_on_demo_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch)
    calls = _capture_issue(monkeypatch)
    async with _client() as c:
        r = await c.post("/internal/v1/demo/session", headers={"X-DeployAI-Internal-Key": INTERNAL_KEY})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["access_token"] == "demo-access-jwt"
    assert body["refresh_token"] == "demo-refresh"
    # Default TTL: DEPLOYAI_DEMO_SESSION_TTL unset → 900 s, same as before.
    assert body["expires_in"] == 900
    assert body["tenant_id"] == DEMO_TENANT
    assert body["roles"] == ["demo_guest"]
    # The caller cannot influence roles / tenant / user — all come from settings.
    assert calls == [(uuid.UUID(DEMO_TENANT), uuid.UUID(DEMO_USER), ["demo_guest"], 900)]


@pytest.mark.asyncio
async def test_demo_session_ttl_env_is_honored(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, DEPLOYAI_DEMO_SESSION_TTL="1800")
    calls = _capture_issue(monkeypatch)
    async with _client() as c:
        r = await c.post("/internal/v1/demo/session", headers={"X-DeployAI-Internal-Key": INTERNAL_KEY})
    assert r.status_code == 201, r.text
    assert r.json()["expires_in"] == 1800
    assert calls[0][3] == 1800


@pytest.mark.asyncio
async def test_demo_session_ttl_clamped_to_one_hour(monkeypatch: pytest.MonkeyPatch) -> None:
    _configure(monkeypatch, DEPLOYAI_DEMO_SESSION_TTL="7200")
    calls = _capture_issue(monkeypatch)
    async with _client() as c:
        r = await c.post("/internal/v1/demo/session", headers={"X-DeployAI-Internal-Key": INTERNAL_KEY})
    assert r.status_code == 201, r.text
    assert r.json()["expires_in"] == 3600
    assert calls[0][3] == 3600
