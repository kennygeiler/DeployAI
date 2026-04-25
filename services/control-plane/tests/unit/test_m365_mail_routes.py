"""ASGI tests for M365 mail routes (no Graph)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from control_plane.api.routes.integrations_m365_mail import _safe_return_to_url
from control_plane.auth.jwt_tokens import clear_jwt_key_cache, create_access_token
from control_plane.config.settings import clear_settings_cache
from control_plane.main import app


def _write_rsa(tmp: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_b = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_b = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv = tmp / "m365-mail-priv.pem"
    pub = tmp / "m365-mail-pub.pem"
    priv.write_bytes(priv_b)
    pub.write_bytes(pub_b)
    return priv, pub


def test_safe_return_to_rejects_unsafe_schemes() -> None:
    assert _safe_return_to_url("javascript:alert(1)") is None
    assert _safe_return_to_url("https://ok.example/after") == "https://ok.example/after"
    assert _safe_return_to_url("/relative") is None
    assert _safe_return_to_url("data:text/html,xx") is None


def _bearer(priv: Path, *, tid: uuid.UUID, roles: list[str] | None = None, sub: str = "u1") -> str:
    clear_jwt_key_cache()
    return create_access_token(
        sub=sub,
        tid=str(tid),
        roles=roles or ["deployment_strategist"],
        access_jti="jti-mail-1",
    )


@pytest.mark.asyncio
async def test_m365_mail_connect_503_without_oauth_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    for k in list(os.environ):
        if k.startswith("DEPLOYAI_M365_") or k.startswith("DEPLOYAI_OIDC_"):
            monkeypatch.delenv(k, raising=False)
    clear_settings_cache()
    clear_jwt_key_cache()
    tid = uuid.uuid4()
    try:
        tok = _bearer(priv, tid=tid)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(
                "/integrations/m365-mail/connect",
                params={"tenant_id": str(tid)},
                headers={"Authorization": f"Bearer {tok}"},
                follow_redirects=False,
            )
        assert r.status_code == 503
    finally:
        clear_jwt_key_cache()
        clear_settings_cache()


@pytest.mark.asyncio
async def test_m365_mail_connect_403_tenant_mismatch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    monkeypatch.setenv("DEPLOYAI_OIDC_ISSUER", "https://login.microsoftonline.com/tenant/v2.0")
    monkeypatch.setenv("DEPLOYAI_OIDC_CLIENT_ID", "cid")
    monkeypatch.setenv("DEPLOYAI_OIDC_CLIENT_SECRET", "sec")
    monkeypatch.setenv("DEPLOYAI_M365_MAIL_REDIRECT_URI", "https://cp.example.com/integrations/m365-mail/callback")
    clear_settings_cache()
    clear_jwt_key_cache()
    tok_tid = uuid.uuid4()
    other_tid = uuid.uuid4()
    try:
        tok = _bearer(priv, tid=tok_tid)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(
                "/integrations/m365-mail/connect",
                params={"tenant_id": str(other_tid)},
                headers={"Authorization": f"Bearer {tok}"},
                follow_redirects=False,
            )
        assert r.status_code == 403
    finally:
        clear_jwt_key_cache()
        clear_settings_cache()


@pytest.mark.asyncio
async def test_m365_mail_callback_400_without_cookies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_OIDC_ISSUER", "https://login.microsoftonline.com/tenant/v2.0")
    monkeypatch.setenv("DEPLOYAI_OIDC_CLIENT_ID", "cid")
    monkeypatch.setenv("DEPLOYAI_OIDC_CLIENT_SECRET", "sec")
    monkeypatch.setenv("DEPLOYAI_M365_MAIL_REDIRECT_URI", "https://cp.example.com/integrations/m365-mail/callback")
    clear_settings_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(
                "/integrations/m365-mail/callback",
                params={"code": "c", "state": "s"},
            )
        assert r.status_code == 400
    finally:
        clear_settings_cache()
