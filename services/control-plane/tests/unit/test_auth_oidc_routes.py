"""ASGI tests for OIDC route wiring (no IdP)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

import control_plane.api.routes.auth_oidc as auth_oidc_mod
from control_plane.config.settings import clear_settings_cache
from control_plane.db import get_app_db_session
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


class _NoRowResult:
    def scalar_one_or_none(self) -> None:
        return None


class _NoRowSession:
    """Fake AsyncSession: entra_sub lookup finds nothing (unknown user)."""

    async def execute(self, *_args: object, **_kwargs: object) -> _NoRowResult:
        return _NoRowResult()


@pytest.mark.asyncio
async def test_oidc_callback_403_when_jit_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ticket A1: unknown OIDC subject + DEPLOYAI_OIDC_JIT_ENABLED=0 -> 403 (no JIT insert)."""
    monkeypatch.setenv("DEPLOYAI_OIDC_ISSUER", "https://idp.example.com")
    monkeypatch.setenv("DEPLOYAI_OIDC_CLIENT_ID", "c1")
    monkeypatch.setenv("DEPLOYAI_OIDC_CLIENT_SECRET", "s1")
    monkeypatch.setenv("DEPLOYAI_OIDC_REDIRECT_URI", "https://app.example.com/api/auth/callback/oidc")
    monkeypatch.setenv("DEPLOYAI_OIDC_JIT_ENABLED", "0")
    clear_settings_cache()

    metadata: dict[str, Any] = {
        "authorization_endpoint": "https://idp.example.com/authorize",
        "token_endpoint": "https://idp.example.com/token",
        "issuer": "https://idp.example.com",
        "jwks_uri": "https://idp.example.com/jwks",
    }

    async def fake_metadata(_client: object, _issuer: str) -> dict[str, Any]:
        return metadata

    async def fake_exchange(*_args: object, **_kwargs: object) -> dict[str, Any]:
        return {"id_token": "tok"}

    def fake_jwk_client(_md: dict[str, Any]) -> object:
        return object()

    def fake_verify(_tok: str, _md: dict[str, Any], **_kwargs: object) -> dict[str, Any]:
        return {"sub": "entra|unknown", "nonce": "n1", "email": "unknown@example.com"}

    monkeypatch.setattr(auth_oidc_mod, "fetch_openid_metadata", fake_metadata)
    monkeypatch.setattr(auth_oidc_mod, "exchange_code_for_tokens", fake_exchange)
    monkeypatch.setattr(auth_oidc_mod, "create_jwk_client", fake_jwk_client)
    monkeypatch.setattr(auth_oidc_mod, "verify_id_token", fake_verify)

    async def override_session() -> AsyncIterator[Any]:
        yield _NoRowSession()

    app.dependency_overrides[get_app_db_session] = override_session
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://t",
            cookies={"dep_oidc_state": "st1", "dep_oidc_verifier": "v1", "dep_oidc_nonce": "n1"},
        ) as c:
            r = await c.get(
                "/auth/oidc/callback",
                params={"code": "abc", "state": "st1"},
                follow_redirects=False,
            )
        assert r.status_code == 403
        assert "JIT provisioning is disabled" in r.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_app_db_session, None)
        clear_settings_cache()


@pytest.mark.asyncio
async def test_saml_routes_501_with_oidc_pointer() -> None:
    clear_settings_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get("/auth/saml/login", follow_redirects=False)
        assert r.status_code == 501
        body = r.json()["detail"]
        assert isinstance(body, dict) and body.get("error") == "saml_not_implemented"
    finally:
        clear_settings_cache()
