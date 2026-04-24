"""Epic 3 Story 3-1: M365 calendar OAuth + Graph sync (integration + E2E with mocked Microsoft HTTP)."""

from __future__ import annotations

import uuid
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

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
    priv = tmp / "m365-e2e-priv.pem"
    pub = tmp / "m365-e2e-pub.pem"
    priv.write_bytes(priv_b)
    pub.write_bytes(pub_b)
    return priv, pub


pytestmark = pytest.mark.integration

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

_GRAPH_FIRST_PAGE: dict[str, Any] = {
    "value": [
        {
            "id": "graph-event-99",
            "subject": "Design review",
            "start": {"dateTime": "2026-05-20T15:00:00Z", "timeZone": "UTC"},
            "end": {"dateTime": "2026-05-20T16:00:00Z", "timeZone": "UTC"},
        }
    ],
    "@odata.deltaLink": "https://graph.microsoft.com/v1.0/me/calendarView/delta?token=opaque-delta-1",
}


class _GraphMockAsyncClient:
    """AsyncClient substitute: returns OIDC metadata or Graph pages for any ``get``."""

    def __init__(self, *args: object, **kwargs: object) -> None:
        pass

    async def __aenter__(self) -> SimpleNamespace:
        async def get_impl(url: str, **kwargs: object) -> httpx.Response:
            u = str(url)
            if "openid-configuration" in u or ".well-known" in u:
                return httpx.Response(200, json=_OIDC_JSON)
            if "graph.microsoft.com" in u:
                return httpx.Response(200, json=_GRAPH_FIRST_PAGE)
            return httpx.Response(404, json={"err": u})

        async def post_impl(url: str, **kwargs: object) -> httpx.Response:
            return httpx.Response(200, json={**_TOKEN_JSON, "refresh_token": "refreshed"})

        c = SimpleNamespace()
        c.get = get_impl
        c.post = post_impl
        return c

    async def __aexit__(self, *a: object) -> None:
        return None


@pytest_asyncio.fixture
async def m365_http_client(
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
        "DEPLOYAI_M365_CALENDAR_REDIRECT_URI",
        "https://cp.test/integrations/m365-calendar/callback",
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
        c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'M365 test tenant')"), {"t": str(tid)})


def _cookie_header(parts: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in sorted(parts.items()))


def _bearer(priv: Any, *, tid: uuid.UUID) -> str:
    clear_jwt_key_cache()
    return create_access_token(
        sub="strategist-1", tid=str(tid), roles=["deployment_strategist"], access_jti="m365-jti-1"
    )


@pytest.mark.asyncio
async def test_m365_e2e_connect_callback_and_sync_with_mocked_graph(
    m365_http_client: tuple[AsyncClient, Any], postgres_engine: Engine
) -> None:
    """End-to-end: connect (mocked OIDC metadata) → token callback → sync (mocked Graph) → one canonical row."""
    client, priv = m365_http_client
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    with (
        patch(
            "control_plane.api.routes.integrations_m365_calendar.fetch_metadata",
            AsyncMock(return_value=_OIDC_JSON),
        ),
        patch(
            "control_plane.api.routes.integrations_m365_calendar.exchange_delegation_code",
            AsyncMock(return_value=_TOKEN_JSON),
        ),
    ):
        r0 = await client.get(
            "/integrations/m365-calendar/connect",
            params={"tenant_id": str(tid)},
            headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
            follow_redirects=False,
        )
    assert r0.status_code == 302
    assert "login.microsoftonline.com" in (r0.headers.get("location") or "")
    st = r0.cookies.get("dep_m365_state")
    ver = r0.cookies.get("dep_m365_verifier")
    iid = r0.cookies.get("dep_m365_integration")
    assert st and ver and iid
    ch = _cookie_header(
        {
            "dep_m365_state": st,
            "dep_m365_verifier": ver,
            "dep_m365_integration": iid,
        }
    )
    with (
        patch(
            "control_plane.api.routes.integrations_m365_calendar.fetch_metadata",
            AsyncMock(return_value=_OIDC_JSON),
        ),
        patch(
            "control_plane.api.routes.integrations_m365_calendar.exchange_delegation_code",
            AsyncMock(return_value=_TOKEN_JSON),
        ),
    ):
        r1 = await client.get(
            "/integrations/m365-calendar/callback",
            params={"code": "auth-code-xyz", "state": st},
            headers={"Cookie": ch},
        )
    assert r1.status_code == 200
    body = r1.json()
    assert body.get("status") == "connected"
    integ_id = body["integration_id"]

    with patch("control_plane.services.m365_calendar_sync.httpx.AsyncClient", _GraphMockAsyncClient):
        r2 = await client.post(
            f"/integrations/m365-calendar/{integ_id}/sync",
            headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
        )
    assert r2.status_code == 200, r2.text
    assert r2.json().get("inserted") == 1
    assert r2.json().get("delta_link") is not None

    with postgres_engine.begin() as cx:
        n = cx.execute(
            text(
                "SELECT count(*)::int FROM canonical_memory_events "
                "WHERE tenant_id = CAST(:t AS uuid) AND event_type = 'calendar.event' "
                "AND source_ref = :ref"
            ),
            {
                "t": str(tid),
                "ref": "graph:calendar_event:graph-event-99",
            },
        ).scalar_one()
    assert int(n) == 1


@pytest.mark.asyncio
async def test_m365_sync_idempotent_second_run_zero_inserts(
    m365_http_client: tuple[AsyncClient, Any], postgres_engine: Engine
) -> None:
    """Two syncs with same mocked Graph body: first inserts 1, second inserts 0 (idempotent)."""
    client, priv = m365_http_client
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    with (
        patch(
            "control_plane.api.routes.integrations_m365_calendar.fetch_metadata",
            AsyncMock(return_value=_OIDC_JSON),
        ),
        patch(
            "control_plane.api.routes.integrations_m365_calendar.exchange_delegation_code",
            AsyncMock(return_value=_TOKEN_JSON),
        ),
    ):
        r0 = await client.get(
            "/integrations/m365-calendar/connect",
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
            "control_plane.api.routes.integrations_m365_calendar.fetch_metadata",
            AsyncMock(return_value=_OIDC_JSON),
        ),
        patch(
            "control_plane.api.routes.integrations_m365_calendar.exchange_delegation_code",
            AsyncMock(return_value=_TOKEN_JSON),
        ),
    ):
        r1 = await client.get(
            "/integrations/m365-calendar/callback",
            params={"code": "c2", "state": st},
            headers={"Cookie": ch},
        )
    assert r1.status_code == 200
    integ_id = r1.json()["integration_id"]

    with patch("control_plane.services.m365_calendar_sync.httpx.AsyncClient", _GraphMockAsyncClient):
        a = await client.post(
            f"/integrations/m365-calendar/{integ_id}/sync",
            headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
        )
        b = await client.post(
            f"/integrations/m365-calendar/{integ_id}/sync",
            headers={"Authorization": f"Bearer {_bearer(priv, tid=tid)}"},
        )
    assert a.json().get("inserted") == 1
    assert b.json().get("inserted") == 0
