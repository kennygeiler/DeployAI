"""Slack OAuth v2 (install to workspace) helper."""

from __future__ import annotations

import urllib.parse
from typing import Any

import httpx

from control_plane.config.settings import ControlPlaneSettings

SLACK_OAUTH_AUTH = "https://slack.com/oauth/v2/authorize"
SLACK_OAUTH_ACCESS = "https://slack.com/api/oauth.v2.access"
SLACK_CONVERSATIONS_INFO = "https://slack.com/api/conversations.info"

# Scopes: read channel/group/im/mpim history for message events; team + users for resolution.
# groups:read covers conversations.info on private channels (SL1 pending-channel names).
DEFAULT_BOT_SCOPES = (
    "channels:history,channels:read,groups:history,groups:read,im:history,mpim:history,users:read,team:read,chat:write"
)


def slack_oauth_creds(s: ControlPlaneSettings) -> tuple[str, str, str] | None:
    cid = (s.slack_client_id or "").strip()
    sec = (s.slack_client_secret or "").strip()
    redir = (s.slack_redirect_uri or "").strip()
    if not (cid and sec and redir):
        return None
    return (cid, sec, redir)


def build_slack_install_url(*, client_id: str, redirect_uri: str, state: str, scope: str = DEFAULT_BOT_SCOPES) -> str:
    q: dict[str, str] = {
        "client_id": client_id,
        "scope": scope,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{SLACK_OAUTH_AUTH}?{urllib.parse.urlencode(q)}"


async def exchange_slack_oauth(
    client: httpx.AsyncClient, *, code: str, client_id: str, client_secret: str, redirect_uri: str
) -> dict[str, Any]:
    r = await client.post(
        SLACK_OAUTH_ACCESS,
        data={
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=30.0,
    )
    if r.is_error:
        raise ValueError(f"Slack oauth.v2.access failed: {r.status_code} {r.text[:400]}")
    data: dict[str, Any] = r.json()
    if not data.get("ok"):
        raise ValueError(f"Slack API error: {data.get('error', data)}")
    return data


async def fetch_slack_channel_name(client: httpx.AsyncClient, *, token: str, channel_id: str) -> str:
    """Best-effort ``conversations.info`` lookup; returns ``""`` when unavailable."""
    r = await client.get(
        SLACK_CONVERSATIONS_INFO,
        params={"channel": channel_id},
        headers={"Authorization": f"Bearer {token}"},
        timeout=10.0,
    )
    if r.is_error:
        return ""
    data: dict[str, Any] = r.json()
    if not data.get("ok"):
        return ""
    ch = data.get("channel")
    if not isinstance(ch, dict):
        return ""
    return str(ch.get("name") or "")
