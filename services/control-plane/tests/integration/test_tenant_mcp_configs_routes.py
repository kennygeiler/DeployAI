"""Integration: Phase 5 Wave 2E — ``tenant_mcp_configs`` internal CP routes.

Covers (scope-v2 §9.1, threat-model §3.4 + §5.4):

1. Auth: missing internal API key → 401.
2. CRUD happy path: create → list → get → patch → delete; response never
   includes the raw token.
3. Token encryption round-trip: the BYTEA written to the row is not equal
   to the plaintext token bytes, and ``has_auth_token`` is True in the
   response.
4. Audit: a create emits exactly one ``mcp_config_created`` ledger row
   whose detail JSON does NOT contain the secret value.
5. RLS: tenant A cannot list / get / patch tenant B's configs.
6. Connector catalog rejection: POST with an unknown connector → 422.
7. Unique constraint: two creates with the same ``name`` for one tenant
   → second returns 409.
8. OAuth start for slack with missing env → 503.
9. OAuth callback for an unsupported connector → 501.

Run with ``uv run pytest -m integration``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(
        hide_password=False,
    )


def _ins_tenant(engine: Engine, tid: uuid.UUID, *, name: str = "mcp-routes") -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, :n) ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid), "n": name},
        )


@pytest_asyncio.fixture
async def mcp_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "mcp-test-key")
    # Ensure the Slack OAuth env vars are unset by default; the
    # "503 when not configured" test relies on it.
    monkeypatch.delenv("DEPLOYAI_SLACK_CLIENT_ID", raising=False)
    monkeypatch.delenv("DEPLOYAI_SLACK_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("DEPLOYAI_SLACK_REDIRECT_URI", raising=False)
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "mcp-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_missing_internal_key_returns_401(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    # Strip the header just for this request.
    r = await mcp_client.get(
        f"/internal/v1/tenants/{tid}/mcp_configs",
        headers={"X-DeployAI-Internal-Key": ""},
    )
    assert r.status_code == 401, r.text


# ---------------------------------------------------------------------------
# CRUD happy path + no token in response
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_crud_happy_path_never_echoes_token(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    secret = "xoxb-super-secret-token-do-not-echo"

    # CREATE
    r = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs",
        json={
            "name": "Acme Slack",
            "connector_kind": "slack",
            "endpoint": "https://slack-mcp.example.com/sse",
            "auth_token": secret,
            "allowed_tools": ["search_messages"],
        },
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "Acme Slack"
    assert created["has_auth_token"] is True
    assert "auth_token" not in created
    assert "encrypted_auth_token" not in created
    assert secret not in r.text
    cid = created["id"]

    # LIST
    r2 = await mcp_client.get(f"/internal/v1/tenants/{tid}/mcp_configs")
    assert r2.status_code == 200
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0]["id"] == cid
    assert rows[0]["has_auth_token"] is True
    assert secret not in r2.text

    # GET
    r3 = await mcp_client.get(f"/internal/v1/tenants/{tid}/mcp_configs/{cid}")
    assert r3.status_code == 200
    assert r3.json()["id"] == cid
    assert secret not in r3.text

    # PATCH (rename + change allowed_tools, no token rotation)
    r4 = await mcp_client.patch(
        f"/internal/v1/tenants/{tid}/mcp_configs/{cid}",
        json={"name": "Acme Slack v2", "allowed_tools": ["search_messages", "post_message"]},
    )
    assert r4.status_code == 200, r4.text
    patched = r4.json()
    assert patched["name"] == "Acme Slack v2"
    assert patched["allowed_tools"] == ["search_messages", "post_message"]
    assert patched["has_auth_token"] is True  # preserved

    # DELETE
    r5 = await mcp_client.delete(f"/internal/v1/tenants/{tid}/mcp_configs/{cid}")
    assert r5.status_code == 204

    r6 = await mcp_client.get(f"/internal/v1/tenants/{tid}/mcp_configs/{cid}")
    assert r6.status_code == 404


# ---------------------------------------------------------------------------
# Token encryption round-trip
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_token_is_encrypted_on_disk(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    secret = "t-secret"
    r = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs",
        json={
            "name": "Acme Slack",
            "connector_kind": "slack",
            "endpoint": "https://slack-mcp.example.com/sse",
            "auth_token": secret,
        },
    )
    assert r.status_code == 201, r.text
    cid = uuid.UUID(r.json()["id"])

    # Inspect the row directly (superuser; bypasses RLS).
    with postgres_engine.connect() as conn:
        row = conn.execute(
            text("SELECT encrypted_auth_token FROM tenant_mcp_configs WHERE id = :id"),
            {"id": str(cid)},
        ).one()
    ciphertext = bytes(row.encrypted_auth_token)
    assert ciphertext, "encrypted_auth_token should not be empty"
    assert ciphertext != secret.encode("utf-8")
    assert secret.encode("utf-8") not in ciphertext


# ---------------------------------------------------------------------------
# Audit: create emits one mcp_config_created with no token in detail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_emits_audit_event_without_secret(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    secret = "xoxb-needle-in-haystack-9f3a2"
    r = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs",
        json={
            "name": "Acme Slack",
            "connector_kind": "slack",
            "endpoint": "https://slack-mcp.example.com/sse",
            "auth_token": secret,
        },
    )
    assert r.status_code == 201, r.text

    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id, summary, detail::text AS detail_text "
                "FROM ledger_events "
                "WHERE tenant_id = :t AND source_kind = 'mcp_config_created'"
            ),
            {"t": str(tid)},
        ).all()
    assert len(rows) == 1, f"expected exactly 1 mcp_config_created row; got {len(rows)}"
    assert "Acme Slack" in rows[0].summary
    # Defense-in-depth: the scrubber should also strip a hypothetical
    # ``auth_token`` key out of detail, but the route never includes it.
    assert secret not in rows[0].detail_text


# ---------------------------------------------------------------------------
# RLS — tenant A cannot see tenant B's configs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_access(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a, name="tenant-a")
    _ins_tenant(postgres_engine, tid_b, name="tenant-b")

    r = await mcp_client.post(
        f"/internal/v1/tenants/{tid_a}/mcp_configs",
        json={
            "name": "A only",
            "connector_kind": "slack",
            "endpoint": "https://a.example.com/sse",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    # Tenant B can't list it.
    r_list = await mcp_client.get(f"/internal/v1/tenants/{tid_b}/mcp_configs")
    assert r_list.status_code == 200
    assert r_list.json() == []

    # Tenant B can't get it (404 because RLS makes the row invisible).
    r_get = await mcp_client.get(f"/internal/v1/tenants/{tid_b}/mcp_configs/{cid}")
    assert r_get.status_code == 404

    # Tenant B can't patch it.
    r_patch = await mcp_client.patch(
        f"/internal/v1/tenants/{tid_b}/mcp_configs/{cid}",
        json={"name": "smuggled"},
    )
    assert r_patch.status_code == 404


# ---------------------------------------------------------------------------
# Connector catalog rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_connector_kind_returns_422(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs",
        json={
            "name": "bad",
            "connector_kind": "dropbox",
            "endpoint": "https://x.example.com/sse",
        },
    )
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------------------
# Unique-constraint conflict
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_duplicate_name_returns_409(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    body = {
        "name": "Acme Slack",
        "connector_kind": "slack",
        "endpoint": "https://slack-mcp.example.com/sse",
    }
    r1 = await mcp_client.post(f"/internal/v1/tenants/{tid}/mcp_configs", json=body)
    assert r1.status_code == 201
    r2 = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs",
        json={**body, "connector_kind": "linear"},
    )
    assert r2.status_code == 409, r2.text


# ---------------------------------------------------------------------------
# OAuth start for slack without env → 503
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth_start_slack_without_env_returns_503(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs",
        json={
            "name": "Acme Slack",
            "connector_kind": "slack",
            "endpoint": "https://slack-mcp.example.com/sse",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r2 = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs/{cid}/oauth/start",
        json={"redirect_uri": "https://app.example.com/oauth/return"},
    )
    assert r2.status_code == 503, r2.text


# ---------------------------------------------------------------------------
# OAuth callback for unsupported connector → 501
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth_callback_unsupported_connector_returns_501(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs",
        json={
            "name": "Acme Linear",
            "connector_kind": "linear",
            "endpoint": "https://linear-mcp.example.com/sse",
        },
    )
    assert r.status_code == 201, r.text
    cid = r.json()["id"]

    r2 = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs/{cid}/oauth/callback",
        json={"code": "stub", "state": "stub"},
    )
    assert r2.status_code == 501, r2.text


@pytest.mark.asyncio
async def test_oauth_start_unsupported_connector_returns_501(
    mcp_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs",
        json={
            "name": "Acme Notion",
            "connector_kind": "notion",
            "endpoint": "https://notion-mcp.example.com/sse",
        },
    )
    assert r.status_code == 201
    cid = r.json()["id"]

    r2 = await mcp_client.post(
        f"/internal/v1/tenants/{tid}/mcp_configs/{cid}/oauth/start",
        json={"redirect_uri": "https://app.example.com/oauth/return"},
    )
    assert r2.status_code == 501, r2.text
