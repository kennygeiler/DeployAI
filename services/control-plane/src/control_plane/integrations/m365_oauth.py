"""Microsoft identity + Graph delegated OAuth (Epic 3 Story 3-1)."""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

from control_plane.auth.oidc_flow import OidcError, fetch_openid_metadata, pkce_pair
from control_plane.config.settings import ControlPlaneSettings

GRAPH_SCOPES: str = "offline_access https://graph.microsoft.com/Calendars.Read https://graph.microsoft.com/User.Read"


def m365_oauth_creds(s: ControlPlaneSettings) -> tuple[str, str, str, str] | None:
    """Return ``(issuer, client_id, client_secret, m365_redirect_uri)`` or ``None`` if incomplete."""
    iss = (s.m365_oauth_issuer or s.oidc_issuer or "").strip()
    cid = (s.m365_oauth_client_id or s.oidc_client_id or "").strip()
    sec = (s.m365_oauth_client_secret or s.oidc_client_secret or "").strip()
    redir = (s.m365_calendar_redirect_uri or "").strip()
    if not (iss and cid and sec and redir):
        return None
    return (iss, cid, sec, redir)


def build_graph_delegate_authorization_url(
    metadata: dict[str, Any],
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
) -> str:
    q: dict[str, str] = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "response_mode": "query",
        "scope": GRAPH_SCOPES,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_ep = str(metadata["authorization_endpoint"])
    return f"{auth_ep}?{urllib.parse.urlencode(q)}"


async def exchange_delegation_code(
    httpx_client: httpx.AsyncClient,
    token_endpoint: str,
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
        token_endpoint,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    if r.is_error:
        raise OidcError(f"token endpoint failed: {r.status_code} {r.text[:500]}")
    body: dict[str, Any] = r.json()
    if "access_token" not in body or not body["access_token"]:
        raise OidcError("token response missing access_token")
    return body


async def refresh_delegation_access(
    httpx_client: httpx.AsyncClient,
    token_endpoint: str,
    *,
    refresh_token: str,
    client_id: str,
    client_secret: str,
) -> dict[str, Any]:
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": GRAPH_SCOPES,
    }
    r = await httpx_client.post(
        token_endpoint,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    if r.is_error:
        raise OidcError(f"token refresh failed: {r.status_code} {r.text[:500]}")
    body: dict[str, Any] = r.json()
    if "access_token" not in body or not body["access_token"]:
        raise OidcError("refresh response missing access_token")
    return body


async def fetch_metadata(httpx_client: httpx.AsyncClient, issuer: str) -> dict[str, Any]:
    return await fetch_openid_metadata(httpx_client, issuer)


__all__ = [
    "GRAPH_SCOPES",
    "build_graph_delegate_authorization_url",
    "exchange_delegation_code",
    "fetch_metadata",
    "m365_oauth_creds",
    "pkce_pair",
    "refresh_delegation_access",
]
