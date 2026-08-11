"""Integration: per-tenant service token mint/list/revoke + auth flow (A4)."""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.domain.app_identity.service_tokens import RAW_TOKEN_PREFIX
from control_plane.main import app

pytestmark = pytest.mark.integration

_GLOBAL_KEY = "svc-token-test-global-key"


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", _GLOBAL_KEY)
    clear_engine_cache()
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://test")
    c.headers["X-DeployAI-Internal-Key"] = _GLOBAL_KEY
    try:
        yield c
    finally:
        await c.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine, name: str) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"), {"t": str(tid), "n": name})
    return tid


@pytest.mark.asyncio
async def test_mint_list_revoke_lifecycle(postgres_engine: Engine, client: AsyncClient) -> None:
    tenant = _seed_tenant(postgres_engine, "svc-tokens")

    # Mint: raw token returned exactly once, prefixed, secret not persisted.
    resp = await client.post(
        "/internal/v1/tenant/service-tokens",
        params={"tenant_id": str(tenant)},
        json={"name": "bff"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    raw = body["raw_token"]
    assert raw.startswith(RAW_TOKEN_PREFIX)
    token_id = body["service_token"]["id"]
    assert body["service_token"]["revoked_at"] is None
    with postgres_engine.connect() as conn:
        stored = conn.execute(
            text("SELECT hashed_key FROM internal_service_tokens WHERE id = :i"), {"i": token_id}
        ).scalar_one()
    assert raw not in stored

    # Duplicate name for the same tenant conflicts.
    resp = await client.post(
        "/internal/v1/tenant/service-tokens",
        params={"tenant_id": str(tenant)},
        json={"name": "bff"},
    )
    assert resp.status_code == 409

    # List exposes metadata only.
    resp = await client.get("/internal/v1/tenant/service-tokens", params={"tenant_id": str(tenant)})
    assert resp.status_code == 200
    listed = resp.json()["service_tokens"]
    assert [t["id"] for t in listed] == [token_id]
    assert "raw_token" not in listed[0]
    assert "hashed_key" not in listed[0]

    # Revoke; idempotent listing shows the timestamp.
    resp = await client.delete(
        f"/internal/v1/tenant/service-tokens/{token_id}",
        params={"tenant_id": str(tenant)},
    )
    assert resp.status_code == 204
    resp = await client.get("/internal/v1/tenant/service-tokens", params={"tenant_id": str(tenant)})
    assert resp.json()["service_tokens"][0]["revoked_at"] is not None


@pytest.mark.asyncio
async def test_minted_token_authenticates_and_scopes(
    postgres_engine: Engine,
    client: AsyncClient,
) -> None:
    tenant_a = _seed_tenant(postgres_engine, "svc-a")
    tenant_b = _seed_tenant(postgres_engine, "svc-b")

    resp = await client.post(
        "/internal/v1/tenant/service-tokens",
        params={"tenant_id": str(tenant_a)},
        json={"name": "worker"},
    )
    raw_a = resp.json()["raw_token"]

    # The minted token authenticates a converted tenant-scoped route.
    resp = await client.get(
        "/internal/v1/temporal-insights",
        params={"tenant_id": str(tenant_a)},
        headers={"X-DeployAI-Internal-Key": raw_a},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []

    # The same token naming another tenant is rejected with 403.
    resp = await client.get(
        "/internal/v1/temporal-insights",
        params={"tenant_id": str(tenant_b)},
        headers={"X-DeployAI-Internal-Key": raw_a},
    )
    assert resp.status_code == 403

    # A garbage token is 401.
    resp = await client.get(
        "/internal/v1/temporal-insights",
        params={"tenant_id": str(tenant_a)},
        headers={"X-DeployAI-Internal-Key": "dpai_svc_deadbeef"},
    )
    assert resp.status_code == 401

    # A tenant token cannot mint further tokens (admin gate is global-key only).
    resp = await client.post(
        "/internal/v1/tenant/service-tokens",
        params={"tenant_id": str(tenant_a)},
        json={"name": "escalation"},
        headers={"X-DeployAI-Internal-Key": raw_a},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_legacy_global_key_logs_structured_warning(
    postgres_engine: Engine,
    client: AsyncClient,
    caplog: pytest.LogCaptureFixture,
) -> None:
    tenant = _seed_tenant(postgres_engine, "svc-legacy")
    with caplog.at_level(logging.WARNING, logger="control_plane.config.internal_auth"):
        resp = await client.get(
            "/internal/v1/temporal-insights",
            params={"tenant_id": str(tenant)},
        )
    assert resp.status_code == 200
    warnings = [r for r in caplog.records if "legacy_global_key_used" in r.message]
    assert warnings, "expected a structured deprecation warning per legacy-key use"
    assert getattr(warnings[0], "requested_tenant_id", None) == str(tenant)
