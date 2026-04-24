"""Google OAuth 2.0 + token refresh (Gmail API delegated access)."""

from __future__ import annotations

import urllib.parse
from typing import Any, cast

import httpx

from control_plane.config.settings import ControlPlaneSettings

GMAIL_OAUTH_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_TOKEN = "https://oauth2.googleapis.com/token"
# Gmail + OIDC for stable subject; offline refresh via access_type=offline
GMAIL_DEFAULT_SCOPES = "https://www.googleapis.com/auth/gmail.readonly openid email profile"


def gmail_oauth_creds(s: ControlPlaneSettings) -> tuple[str, str, str] | None:
    """Return (client_id, client_secret, redirect_uri) if configured."""
    cid = (s.google_gmail_client_id or "").strip()
    sec = (s.google_gmail_client_secret or "").strip()
    redir = (s.google_gmail_redirect_uri or "").strip()
    if not (cid and sec and redir):
        return None
    return (cid, sec, redir)


def build_gmail_authorization_url(
    *,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scope: str = GMAIL_DEFAULT_SCOPES,
) -> str:
    q: dict[str, str] = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": scope,
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{GMAIL_OAUTH_AUTH}?{urllib.parse.urlencode(q)}"


async def exchange_gmail_code(
    client: httpx.AsyncClient,
    *,
    code: str,
    redirect_uri: str,
    client_id: str,
    client_secret: str,
    code_verifier: str,
) -> dict[str, Any]:
    r = await client.post(
        GMAIL_TOKEN,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    if r.is_error:
        raise ValueError(f"Gmail token exchange failed: {r.status_code} {r.text[:400]}")
    return cast(dict[str, Any], r.json())


async def refresh_gmail_access(
    client: httpx.AsyncClient, *, client_id: str, client_secret: str, refresh_token: str
) -> dict[str, Any]:
    r = await client.post(
        GMAIL_TOKEN,
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    if r.is_error:
        raise ValueError(f"Gmail token refresh failed: {r.status_code} {r.text[:400]}")
    return cast(dict[str, Any], r.json())
