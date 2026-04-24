"""SCIM 2-3: bearer auth, user CRUD, error envelope."""

from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app

_SCIM = Path(__file__).resolve().parents[1] / "fixtures" / "scim"


def _async_database_url_from_engine(postgres_engine: Engine) -> str:
    u = postgres_engine.url.set(drivername="postgresql+psycopg")
    return u.render_as_string(hide_password=False)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@pytest_asyncio.fixture
async def scim_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, uuid.UUID]]:
    token = "integration-scim-bearer"
    tid = uuid.uuid4()
    h = _token_hash(token)
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO app_tenants (id, name, scim_bearer_token_hash) VALUES (:id, :n, :h)"
            ),
            {"id": tid, "n": "integration-scim-tenant", "h": h},
        )
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.headers["Authorization"] = f"Bearer {token}"
            client.headers["Content-Type"] = "application/json"
            yield client, tid
    finally:
        with postgres_engine.begin() as conn:
            conn.execute(text("DELETE FROM app_tenants WHERE id = :id"), {"id": tid})
        clear_engine_cache()


@pytest.mark.integration
async def test_scim_lifecycle_unauthorized(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            r = await c.get("/scim/v2/Users", headers={"Authorization": "Bearer wrong"})
    finally:
        clear_engine_cache()
    assert r.status_code == 401
    b = r.json()
    d = b["detail"] if isinstance(b.get("detail"), dict) else b
    assert d["schemas"] == ["urn:ietf:params:scim:api:messages:2.0:Error"]


@pytest.mark.integration
async def test_scim_lifecycle(
    scim_client: tuple[AsyncClient, uuid.UUID], postgres_engine: Engine
) -> None:
    client, tid = scim_client
    with (_SCIM / "create_user.json").open(encoding="utf-8") as f:
        create = json.load(f)
    r = await client.post("/scim/v2/Users", json=create)
    assert r.status_code == 201, r.text
    loc = r.headers.get("location")
    assert loc and "Users/" in (loc or "")
    body = r.json()
    assert body["userName"] == "jane.entra"
    assert body.get("active") is True
    user_id = body["id"]
    uu = uuid.UUID(user_id)
    with postgres_engine.begin() as conn:
        row = (
            conn.execute(
                text("SELECT user_name, scim_external_id, active FROM app_users WHERE id = :id AND tenant_id = :t"),
                {"id": uu, "t": tid},
            )
            .mappings()
            .one()
        )
    assert row["user_name"] == "jane.entra"
    assert row["scim_external_id"] == "entra-obj-001"

    list_r = await client.get("/scim/v2/Users", params={"startIndex": 1, "count": 50})
    assert list_r.status_code == 200, list_r.text
    jl = list_r.json()
    assert jl["totalResults"] >= 1
    assert any(x["id"] == user_id for x in jl["Resources"])

    fl = await client.get(
        "/scim/v2/Users",
        params={'filter': 'userName eq "jane.entra"'},
    )
    assert fl.status_code == 200
    assert any(x["id"] == user_id for x in fl.json()["Resources"])

    with (_SCIM / "patch_operations.json").open(encoding="utf-8") as f:
        patch = json.load(f)
    p = await client.patch(f"/scim/v2/Users/{user_id}", json=patch)
    assert p.status_code == 200, p.text
    assert p.json()["active"] is False

    d = await client.delete(f"/scim/v2/Users/{user_id}")
    assert d.status_code == 204, d.text
    with postgres_engine.begin() as conn:
        a = (
            conn.execute(
                text("SELECT active FROM app_users WHERE id = :id"),
                {"id": uu},
            )
            .scalar_one()
        )
    assert a is False
