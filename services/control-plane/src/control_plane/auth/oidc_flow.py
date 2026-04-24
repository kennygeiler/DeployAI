"""Microsoft Entra-compatible OpenID Connect helpers (Story 2-2, OIDC + PKCE)."""

from __future__ import annotations

import ssl
import urllib.parse
from typing import Any

import httpx
import jwt
from authlib.common.security import generate_token
from authlib.oauth2.rfc7636 import create_s256_code_challenge
from jwt import PyJWKClient, PyJWKClientError
from jwt.exceptions import InvalidTokenError


class OidcError(Exception):
    """OpenID connect flow or token verification failed."""


def pkce_pair() -> tuple[str, str]:
    """Return (``code_verifier``, ``code_challenge``) for RFC 7636 S256."""
    code_verifier = generate_token(48)
    return code_verifier, create_s256_code_challenge(code_verifier)


async def fetch_openid_metadata(httpx_client: httpx.AsyncClient, issuer: str) -> dict[str, Any]:
    iss = issuer.rstrip("/")
    url = f"{iss}/.well-known/openid-configuration"
    r = await httpx_client.get(url, follow_redirects=True, timeout=20.0)
    if r.is_error:
        raise OidcError(f"openid configuration fetch failed: {r.status_code} {r.text[:200]}")
    data: dict[str, Any] = r.json()
    for key in ("authorization_endpoint", "token_endpoint", "issuer", "jwks_uri"):
        if key not in data or not data[key]:
            raise OidcError(f"openid metadata missing {key!r}")
    return data


def build_authorization_url(
    *,
    metadata: dict[str, Any],
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    nonce: str,
) -> str:
    q = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "response_mode": "query",
        "nonce": nonce,
    }
    auth_ep = str(metadata["authorization_endpoint"])
    return f"{auth_ep}?{urllib.parse.urlencode(q)}"


async def exchange_code_for_tokens(
    httpx_client: httpx.AsyncClient,
    metadata: dict[str, Any],
    *,
    code: str,
    redirect_uri: str,
    code_verifier: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    r = await httpx_client.post(
        str(metadata["token_endpoint"]),
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=20.0,
    )
    if r.is_error:
        raise OidcError(f"token endpoint failed: {r.status_code} {r.text[:300]}")
    body: dict[str, Any] = r.json()
    if "id_token" not in body or not isinstance(body["id_token"], str):
        raise OidcError("token response missing id_token")
    return body


def verify_id_token(
    id_token: str,
    metadata: dict[str, Any],
    *,
    client_id: str,
    jwk_client: PyJWKClient,
) -> dict[str, Any]:
    try:
        signing_key = jwk_client.get_signing_key_from_jwt(id_token)
    except PyJWKClientError as e:
        raise OidcError(f"jwks resolve failed: {e}") from e
    try:
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "RS384", "RS512"],
            audience=client_id,
            issuer=str(metadata["issuer"]),
        )
    except InvalidTokenError as e:
        raise OidcError(f"invalid id_token: {e}") from e
    if not isinstance(claims, dict):
        raise OidcError("id_token claims not a dict")
    return dict(claims)


def create_jwk_client(well_known: dict[str, Any]) -> PyJWKClient:
    jwks_uri = str(well_known["jwks_uri"])
    # SSL context for JWKs fetch; Entra is public internet.
    return PyJWKClient(
        jwks_uri,
        ssl_context=ssl.create_default_context(),
        cache_jwk_set=True,
        max_cached_keys=16,
    )
