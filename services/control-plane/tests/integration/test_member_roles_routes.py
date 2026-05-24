"""Sprint 6 inc 2 — tenant-scoped custom engagement-member roles (integration)."""

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
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def m_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "mr-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "mr-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'member-roles-test')"),
            {"t": str(tid)},
        )
    return tid


def _seed_user(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    uid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_users (id, tenant_id, user_name) VALUES (:u, :t, :n)"),
            {"u": str(uid), "t": str(tenant_id), "n": f"user-{uid.hex[:8]}"},
        )
    return uid


@pytest.mark.asyncio
async def test_list_returns_builtin_when_no_custom(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await m_client.get(f"/internal/v1/tenants/{tid}/member-roles")
    assert r.status_code == 200, r.text
    body = r.json()
    names = [b["name"] for b in body["builtin"]]
    assert names == ["fde", "deployment_strategist", "biz_dev"]
    assert body["custom"] == []


@pytest.mark.asyncio
async def test_crud_round_trip(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    created = await m_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "clinical_lead", "label": "Clinical lead", "description": "Owns clinical workflows"},
    )
    assert created.status_code == 201, created.text
    role = created.json()
    assert role["name"] == "clinical_lead"
    assert role["label"] == "Clinical lead"
    assert role["description"] == "Owns clinical workflows"
    rid = role["id"]

    listed = await m_client.get(f"/internal/v1/tenants/{tid}/member-roles")
    assert listed.status_code == 200
    body = listed.json()
    assert len(body["custom"]) == 1
    assert body["custom"][0]["name"] == "clinical_lead"

    updated = await m_client.put(
        f"/internal/v1/tenants/{tid}/member-roles/{rid}",
        json={"label": "Clinical Lead", "description": None},
    )
    assert updated.status_code == 200
    assert updated.json()["label"] == "Clinical Lead"
    assert updated.json()["description"] is None

    deleted = await m_client.delete(f"/internal/v1/tenants/{tid}/member-roles/{rid}")
    assert deleted.status_code == 204

    after = await m_client.get(f"/internal/v1/tenants/{tid}/member-roles")
    assert after.json()["custom"] == []


@pytest.mark.asyncio
async def test_builtin_collision_returns_422(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await m_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "fde", "label": "Whatever"},
    )
    assert r.status_code == 422
    assert "built-in" in r.text


@pytest.mark.asyncio
async def test_malformed_name_returns_422(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    for bad in ("Clinical Lead", "1starts_with_digit", "has-dash", "UPPER"):
        r = await m_client.post(
            f"/internal/v1/tenants/{tid}/member-roles",
            json={"name": bad, "label": "x"},
        )
        assert r.status_code == 422, f"expected 422 for name={bad!r}, got {r.status_code}: {r.text}"


@pytest.mark.asyncio
async def test_duplicate_custom_returns_409(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    first = await m_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "clinical_lead", "label": "Clinical lead"},
    )
    assert first.status_code == 201
    dup = await m_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "clinical_lead", "label": "Lead"},
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_delete_in_use_returns_409(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    uid = _seed_user(postgres_engine, tid)

    created = await m_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "clinical_lead", "label": "Clinical lead"},
    )
    assert created.status_code == 201
    rid = created.json()["id"]

    eng = await m_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Health Pilot"})
    assert eng.status_code == 201
    eid = eng.json()["id"]

    add = await m_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "clinical_lead"},
    )
    assert add.status_code == 201, add.text

    del_res = await m_client.delete(f"/internal/v1/tenants/{tid}/member-roles/{rid}")
    assert del_res.status_code == 409
    assert "in use" in del_res.text


@pytest.mark.asyncio
async def test_member_add_accepts_custom_role(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    uid = _seed_user(postgres_engine, tid)

    created = await m_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "sales_engineer", "label": "Sales engineer"},
    )
    assert created.status_code == 201

    eng = await m_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "SaaS"})
    eid = eng.json()["id"]
    rm = await m_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "sales_engineer"},
    )
    assert rm.status_code == 201, rm.text
    assert rm.json()["role"] == "sales_engineer"


@pytest.mark.asyncio
async def test_member_add_still_rejects_unknown_role(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    uid = _seed_user(postgres_engine, tid)
    eng = await m_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "X"})
    eid = eng.json()["id"]
    r = await m_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "made_up_role"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_role_scoping_across_tenants(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    await m_client.post(
        f"/internal/v1/tenants/{tid_a}/member-roles",
        json={"name": "clinical_lead", "label": "Clinical lead"},
    )
    listed_b = await m_client.get(f"/internal/v1/tenants/{tid_b}/member-roles")
    assert listed_b.status_code == 200
    assert listed_b.json()["custom"] == []


@pytest.mark.asyncio
async def test_unknown_tenant_returns_404(m_client: AsyncClient) -> None:
    r = await m_client.get(f"/internal/v1/tenants/{uuid.uuid4()}/member-roles")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_unknown_role_returns_404(m_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await m_client.put(
        f"/internal/v1/tenants/{tid}/member-roles/{uuid.uuid4()}",
        json={"label": "x"},
    )
    assert r.status_code == 404
