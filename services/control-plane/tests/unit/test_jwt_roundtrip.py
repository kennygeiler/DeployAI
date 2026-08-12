from __future__ import annotations

import uuid
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from control_plane.auth.jwt_tokens import clear_jwt_key_cache, create_access_token, verify_access_token
from control_plane.config.settings import clear_settings_cache, get_settings


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
    priv = tmp / "priv.pem"
    pub = tmp / "pub.pem"
    priv.write_bytes(priv_b)
    pub.write_bytes(pub_b)
    return priv, pub


def test_rs256_roundtrip(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    clear_settings_cache()
    clear_jwt_key_cache()
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    get_settings()
    sub, tid, roles = str(uuid.uuid4()), str(uuid.uuid4()), ["platform_admin"]
    tok = create_access_token(sub=sub, tid=tid, roles=roles, access_jti=str(uuid.uuid4()))
    out = verify_access_token(tok)
    assert out["sub"] == sub
    assert out["tid"] == tid
    assert out["roles"] == roles
    clear_jwt_key_cache()
    clear_settings_cache()


def test_expires_in_override_and_normal_ttl_unaffected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``expires_in`` overrides the TTL for that one token; a token minted the
    normal way (no ``expires_in``) keeps ``access_token_ttl_seconds`` even when
    ``DEPLOYAI_DEMO_SESSION_TTL`` is set — the demo TTL only applies where the
    demo mint threads it explicitly."""
    clear_settings_cache()
    clear_jwt_key_cache()
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    monkeypatch.setenv("DEPLOYAI_DEMO_SESSION_TTL", "3600")
    try:
        s = get_settings()
        normal = create_access_token(sub="u", tid="t", roles=["platform_admin"], access_jti=str(uuid.uuid4()))
        out = jwt.decode(normal, options={"verify_signature": False})
        assert out["exp"] - out["iat"] == s.access_token_ttl_seconds == 900

        overridden = create_access_token(
            sub="u", tid="t", roles=["platform_admin"], access_jti=str(uuid.uuid4()), expires_in=1234
        )
        out = jwt.decode(overridden, options={"verify_signature": False})
        assert out["exp"] - out["iat"] == 1234
    finally:
        clear_jwt_key_cache()
        clear_settings_cache()
