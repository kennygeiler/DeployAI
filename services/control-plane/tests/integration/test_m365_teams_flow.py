"""Epic 3 Story 3-3: Teams transcript OAuth + sync (mocked Graph)."""

from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from urllib.parse import urlparse

import httpx
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.auth.jwt_tokens import clear_jwt_key_cache, create_access_token
from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.main import app

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration

TID = "transcript-T999"
EXPECTED_REF = f"graph:meeting_transcript:{TID}"

_OIDC_JSON: dict[str, str] = {
    "authorization_endpoint": "https://login.microsoftonline.com/tenant-id/oauth2/v2.0/authorize",
    "token_endpoint": "https://login.microsoftonline.com/tenant-id/oauth2/v2.0/token",
    "issuer": "https://login.microsoftonline.com/tenant-id/v2.0",
    "jwks_uri": "https://login.microsoftonline.com/tenant-id/discovery/v2.0/keys",
}

_TOKEN_JSON: dict[str, Any] = {
    "access_token": "graph-access",
    "refresh_token": "graph-refresh",
    "expires_in": 3600,
    "token_type": "Bearer",
}

_JOIN = "https://teams.microsoft.com/l/meetup-join/19%3ameeting_XXX/0?context=1"
OMID = "OM123"
_VTT = "WEBVTT\n\n00:00:01.0 --> 00:00:02.0\n<v Pat>Hello team.</v>\n"

_CAL: dict[str, Any] = {
    "value": [
        {
            "id": "cevent-teams-1",
            "iCalUId": "ical-t1",
            "isOnlineMeeting": True,
            "isCancelled": False,
            "subject": "Sync",
            "start": {"dateTime": "2026-01-10T10:00:00.0000000Z", "timeZone": "UTC"},
            "end": {"dateTime": "2026-01-10T10:30:00.0000000Z", "timeZone": "UTC"},
            "onlineMeeting": {"joinUrl": _JOIN, "conferenceId": "123"},
            "attendees": [
                {
                    "emailAddress": {"name": "Pat", "address": "pat@example.com"},
                    "type": "required",
                },
            ],
        }
    ],
    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/calendarView/delta?token=d-teams",
}

_OM_LIST = {"value": [{"id": OMID, "joinWebUrl": _JOIN}]}
_TLIST = {
    "value": [
        {
            "id": TID,
            "meetingId": OMID,
            "endDateTime": "2026-01-10T10:32:00.0000000Z",
        }
    ],
}


def _graph_response(url: str, **kwargs: object) -> httpx.Response:
    u = str(url)
    p = kwargs.get("params")
    p_d = p if isinstance(p, dict) else {}
    if "openid-configuration" in u or ".well-known" in u:
        return httpx.Response(200, json=_OIDC_JSON)
    if "graph.microsoft.com" in u and "calendarView" in u and "delta" in u:
        return httpx.Response(200, json=_CAL)
    path = urlparse(u).path
    if "graph.microsoft.com" in u and path.rstrip("/").endswith("/onlineMeetings"):
        f = p_d.get("$filter")
        if f and "JoinWebUrl" in str(f):
            return httpx.Response(200, json=_OM_LIST)
    if "graph.microsoft.com" in u and path.endswith("/content"):
        return httpx.Response(200, text=_VTT, headers={"content-type": "text/vtt"})
    if "graph.microsoft.com" in u and "onlineMeetings" in u and path.rstrip("/").endswith("transcripts"):
        return httpx.Response(200, json=_TLIST)
    return httpx.Response(404, json={"err": u, "p": str(p_d)[:120]})


class _TeamsGraphMockAsyncClient:
    def __init__(self, *a: object, **k: object) -> None:
        pass

    async def __aenter__(self) -> SimpleNamespace:
        async def get_impl(url: str, **kwargs: object) -> httpx.Response:
            return _graph_response(url, **kwargs)

        async def post_impl(url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(200, json={**_TOKEN_JSON, "refresh_token": "refreshed"})

        async def request_impl(method: str, url: str, **kwargs: object) -> httpx.Response:
            m = str(method).upper()
            if m == "GET":
                return await get_impl(url, **kwargs)
            if m == "POST":
                return await post_impl(url, **kwargs)
            return httpx.Response(405, json={"method": method, "url": str(url)[:200]})

        c = SimpleNamespace()
        c.get = get_impl
        c.post = post_impl
        c.request = request_impl
        return c

    async def __aexit__(self, *a: object) -> None:
        return None


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
    priv = tmp / "m365-teams-e2e-priv.pem"
    pub = tmp / "m365-teams-e2e-pub.pem"
    priv.write_bytes(priv_b)
    pub.write_bytes(pub_b)
    return priv, pub


@pytest_asyncio.fixture
async def m365_teams_http_client(
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    monkeypatch.setenv("DEPLOYAI_OIDC_ISSUER", "https://login.microsoftonline.com/tenant-id/v2.0")
    monkeypatch.setenv("DEPLOYAI_OIDC_CLIENT_ID", "test-client")
    monkeypatch.setenv("DEPLOYAI_OIDC_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv(
        "DEPLOYAI_M365_TEAMS_REDIRECT_URI",
        "https://cp.test/integrations/m365-teams/callback",
    )
    clear_settings_cache()
    clear_jwt_key_cache()
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, priv
    finally:
        clear_jwt_key_cache()
        clear_settings_cache()
        clear_engine_cache()


def _ins_tenant(conn: Engine, tid: uuid.UUID) -> None:
    with conn.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'M365 teams test')"),
            {"t": str(tid)},
        )


def _cookie_header(parts: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in sorted(parts.items()))


def _bearer(priv: Any, *, tid: uuid.UUID) -> str:
    clear_jwt_key_cache()
    return create_access_token(sub="strat-t", tid=str(tid), roles=["deployment_strategist"], access_jti="t-jti")


@pytest.mark.asyncio
async def test_teams_e2e_connect_and_sync(
    m365_teams_http_client: tuple[AsyncClient, Any], postgres_engine: Engine
) -> None:
    client, priv = m365_teams_http_client
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    em = "pat@example.com"
    h = hashlib.sha256(em.encode()).hexdigest()[:16]
    with postgres_engine.begin() as cx:
        cx.execute(
            text(
                "INSERT INTO identity_nodes (tenant_id, canonical_name, primary_email_hash) "
                "VALUES (CAST(:t AS uuid), 'Pat', :h)"
            ),
            {"t": str(tid), "h": h},
        )

    with (
        patch(
            "control_plane.api.routes.integrations_m365_teams.fetch_metadata",
            AsyncMock(return_value=_OIDC_JSON),
        ),
        patch(
            "control_plane.api.routes.integrations_m365_teams.exchange_delegation_code",
            AsyncMock(return_value=_TOKEN_JSON),
        ),
    ):
        r0 = await client.get(
            "/integrations/m365-teams/connect",
            params={"tenant_id": str(tid)},
            headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
            follow_redirects=False,
        )
    assert r0.status_code == 302
    st = r0.cookies.get("dep_m365_state")
    assert st and r0.cookies.get("dep_m365_verifier") and r0.cookies.get("dep_m365_integration")
    ch = _cookie_header(
        {
            "dep_m365_state": st,
            "dep_m365_verifier": r0.cookies.get("dep_m365_verifier", "") or "",
            "dep_m365_integration": r0.cookies.get("dep_m365_integration", "") or "",
        }
    )
    with (
        patch(
            "control_plane.api.routes.integrations_m365_teams.fetch_metadata",
            AsyncMock(return_value=_OIDC_JSON),
        ),
        patch(
            "control_plane.api.routes.integrations_m365_teams.exchange_delegation_code",
            AsyncMock(return_value=_TOKEN_JSON),
        ),
    ):
        r1 = await client.get(
            "/integrations/m365-teams/callback", params={"code": "c", "state": st}, headers={"Cookie": ch}
        )
    assert r1.status_code == 200
    integ_id = r1.json()["integration_id"]

    with patch("control_plane.services.m365_teams_transcript_sync.httpx.AsyncClient", _TeamsGraphMockAsyncClient):
        r2 = await client.post(
            f"/integrations/m365-teams/{integ_id}/sync",
            headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
        )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("inserted") == 1
    with postgres_engine.begin() as cx:
        n = cx.execute(
            text(
                "SELECT count(*)::int FROM canonical_memory_events "
                "WHERE tenant_id = CAST(:t AS uuid) AND event_type = 'meeting.transcript' AND source_ref = :r"
            ),
            {"t": str(tid), "r": EXPECTED_REF},
        ).scalar_one()
    assert n == 1
    with postgres_engine.begin() as cx:
        has_id = cx.execute(
            text(
                "SELECT (payload->'participants'->0->'identity_id') IS NOT NULL AS ok FROM "
                "canonical_memory_events WHERE tenant_id = CAST(:t AS uuid) AND source_ref = :r"
            ),
            {"t": str(tid), "r": EXPECTED_REF},
        ).scalar_one()
    assert has_id is True


@pytest.mark.asyncio
async def test_teams_sync_idempotent(m365_teams_http_client: tuple[AsyncClient, Any], postgres_engine: Engine) -> None:
    client, priv = m365_teams_http_client
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    with (
        patch(
            "control_plane.api.routes.integrations_m365_teams.fetch_metadata",
            AsyncMock(return_value=_OIDC_JSON),
        ),
        patch(
            "control_plane.api.routes.integrations_m365_teams.exchange_delegation_code",
            AsyncMock(return_value=_TOKEN_JSON),
        ),
    ):
        r0 = await client.get(
            "/integrations/m365-teams/connect",
            params={"tenant_id": str(tid)},
            headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
            follow_redirects=False,
        )
    st = r0.cookies.get("dep_m365_state")
    assert st
    ch = _cookie_header(
        {
            "dep_m365_state": st,
            "dep_m365_verifier": r0.cookies.get("dep_m365_verifier", "") or "",
            "dep_m365_integration": r0.cookies.get("dep_m365_integration", "") or "",
        }
    )
    with (
        patch(
            "control_plane.api.routes.integrations_m365_teams.fetch_metadata",
            AsyncMock(return_value=_OIDC_JSON),
        ),
        patch(
            "control_plane.api.routes.integrations_m365_teams.exchange_delegation_code",
            AsyncMock(return_value=_TOKEN_JSON),
        ),
    ):
        r1 = await client.get(
            "/integrations/m365-teams/callback", params={"code": "c2", "state": st}, headers={"Cookie": ch}
        )
    integ_id = r1.json()["integration_id"]
    with patch("control_plane.services.m365_teams_transcript_sync.httpx.AsyncClient", _TeamsGraphMockAsyncClient):
        a = await client.post(
            f"/integrations/m365-teams/{integ_id}/sync",
            headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
        )
        b = await client.post(
            f"/integrations/m365-teams/{integ_id}/sync",
            headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
        )
    assert a.json().get("inserted") == 1
    assert b.json().get("inserted") == 0
