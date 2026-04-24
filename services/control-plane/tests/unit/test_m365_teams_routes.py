"""ASGI tests for M365 Teams transcript routes (no Graph)."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from control_plane.api.routes.integrations_m365_teams import _safe_return_to_url
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
    priv = tmp / "m365-teams-priv.pem"
    pub = tmp / "m365-teams-pub.pem"
    priv.write_bytes(priv_b)
    pub.write_bytes(pub_b)
    return priv, pub


def test_safe_return() -> None:
    assert _safe_return_to_url("https://a.example/x") == "https://a.example/x"
    assert _safe_return_to_url("javascript:1") is None


def _bearer(priv: Path, *, tid: uuid.UUID) -> str:
    clear_jwt_key_cache()
    return create_access_token(
        sub="u1", tid=str(tid), roles=["deployment_strategist"], access_jti="jti-t"
    )


@pytest.mark.asyncio
async def test_teams_connect_503(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
            r = await c.get(
                "/integrations/m365-teams/connect",
                params={"tenant_id": str(tid)},
                headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
                follow_redirects=False,
            )
        assert r.status_code == 503
    finally:
        clear_jwt_key_cache()
        clear_settings_cache()
