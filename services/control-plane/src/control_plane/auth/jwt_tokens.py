"""RS256 access JWT issue + verify; multi-PEM verify for key rotation (Story 2-4, NFR76)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt

from control_plane.config.settings import get_settings

_LEEWAY_SEC = 60


@dataclass(frozen=True)
class JwtKeyMaterial:
    private_pem: bytes | None
    public_pems: list[bytes]
    kid: str


@lru_cache(maxsize=1)
def _load_key_material() -> JwtKeyMaterial:
    s = get_settings()
    priv: bytes | None = None
    if s.jwt_private_key_path:
        with open(s.jwt_private_key_path, "rb") as f:
            priv = f.read()
    publics: list[bytes] = []
    for part in s.jwt_public_key_paths.split(","):
        p = part.strip()
        if not p:
            continue
        with open(p, "rb") as f:
            publics.append(f.read())
    if priv is not None and not publics:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.serialization import load_pem_private_key

        k = load_pem_private_key(priv, password=None)
        pub = k.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        publics = [pub]
    if not publics:
        raise RuntimeError(
            "Configure DEPLOYAI_JWT_PUBLIC_KEY_PATHS or DEPLOYAI_JWT_PRIVATE_KEY_PATH to derive a public key for verify"
        )
    return JwtKeyMaterial(private_pem=priv, public_pems=publics, kid=s.jwt_kid)


def clear_jwt_key_cache() -> None:
    _load_key_material.cache_clear()


def create_access_token(
    *,
    sub: str,
    tid: str,
    roles: list[str],
    access_jti: str,
) -> str:
    s = get_settings()
    m = _load_key_material()
    if m.private_pem is None:
        raise RuntimeError("JWT signing requires DEPLOYAI_JWT_PRIVATE_KEY_PATH")
    now = int(time.time())
    payload: dict[str, Any] = {
        "sub": sub,
        "tid": tid,
        "roles": roles,
        "iss": s.jwt_issuer,
        "aud": s.jwt_audience,
        "iat": now,
        "exp": now + s.access_token_ttl_seconds,
        "jti": access_jti,
        "token_use": "access",
    }
    return jwt.encode(
        payload,
        m.private_pem,
        algorithm="RS256",
        headers={"kid": s.jwt_kid},
    )


def verify_access_token(token: str) -> dict[str, Any]:
    s = get_settings()
    m = _load_key_material()
    for pem in m.public_pems:
        try:
            return jwt.decode(
                token,
                pem,
                algorithms=["RS256"],
                audience=s.jwt_audience,
                issuer=s.jwt_issuer,
                leeway=_LEEWAY_SEC,
            )
        except jwt.InvalidTokenError:
            continue
    raise jwt.InvalidTokenError("Access token not verified with any configured public key")
