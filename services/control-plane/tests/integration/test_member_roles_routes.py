"""Tenant custom engagement-member role registry (integration)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.domain.member_roles import BUILTIN_MEMBER_ROLES
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def mr_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
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


def _seed_user(engine: Engine, tenant_id: uuid.UUID, user_name: str = "alice") -> uuid.UUID:
    uid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_users (id, tenant_id, user_name) VALUES (:u, :t, :n)"),
            {"u": str(uid), "t": str(tenant_id), "n": user_name},
        )
    return uid


@pytest.mark.asyncio
async def test_list_returns_builtins_when_no_custom(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await mr_client.get(f"/internal/v1/tenants/{tid}/member-roles")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {b["name"] for b in body["builtin"]} == set(BUILTIN_MEMBER_ROLES)
    assert body["custom"] == []


@pytest.mark.asyncio
async def test_create_list_update_delete_roundtrip(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    created = await mr_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={
            "name": "clinical_lead",
            "label": "Clinical lead",
            "description": "Owns clinical safety sign-off for healthcare deployments.",
        },
    )
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["name"] == "clinical_lead"
    assert row["label"] == "Clinical lead"
    rid = row["id"]

    listed = await mr_client.get(f"/internal/v1/tenants/{tid}/member-roles")
    assert listed.status_code == 200
    assert [c["name"] for c in listed.json()["custom"]] == ["clinical_lead"]

    updated = await mr_client.put(
        f"/internal/v1/tenants/{tid}/member-roles/{rid}",
        json={"label": "Clinical safety lead", "description": None},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["label"] == "Clinical safety lead"
    assert body["description"] is None
    assert body["name"] == "clinical_lead"

    deleted = await mr_client.delete(f"/internal/v1/tenants/{tid}/member-roles/{rid}")
    assert deleted.status_code == 204
    listed2 = await mr_client.get(f"/internal/v1/tenants/{tid}/member-roles")
    assert listed2.json()["custom"] == []


@pytest.mark.asyncio
async def test_create_rejects_builtin_collision(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await mr_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "fde", "label": "Custom FDE"},
    )
    assert r.status_code == 422
    assert "built-in" in r.text


@pytest.mark.asyncio
async def test_create_rejects_malformed_name(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    for bad in ("Clinical_Lead", "1abc", "with-dash", "x" * 60, ""):
        r = await mr_client.post(
            f"/internal/v1/tenants/{tid}/member-roles",
            json={"name": bad, "label": "x"},
        )
        assert r.status_code == 422, f"expected 422 for {bad!r}, got {r.status_code}"


@pytest.mark.asyncio
async def test_create_409_on_duplicate_name(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    await mr_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "sales_engineer", "label": "Sales engineer"},
    )
    dup = await mr_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "sales_engineer", "label": "Other"},
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_delete_in_use_returns_409(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    role_resp = await mr_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "clinical_lead", "label": "Clinical lead"},
    )
    rid = role_resp.json()["id"]
    e_resp = await mr_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Healthcare A"},
    )
    eid = e_resp.json()["id"]
    uid = _seed_user(postgres_engine, tid)
    m_resp = await mr_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "clinical_lead"},
    )
    assert m_resp.status_code == 201, m_resp.text

    blocked = await mr_client.delete(f"/internal/v1/tenants/{tid}/member-roles/{rid}")
    assert blocked.status_code == 409
    assert "in use" in blocked.text


@pytest.mark.asyncio
async def test_member_add_accepts_custom_role(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    await mr_client.post(
        f"/internal/v1/tenants/{tid}/member-roles",
        json={"name": "sales_engineer", "label": "Sales engineer"},
    )
    e_resp = await mr_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "SaaS one"},
    )
    eid = e_resp.json()["id"]
    uid = _seed_user(postgres_engine, tid, user_name="bob")
    r = await mr_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "sales_engineer"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["role"] == "sales_engineer"


@pytest.mark.asyncio
async def test_member_add_still_rejects_unknown_role(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    e_resp = await mr_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Eng"},
    )
    eid = e_resp.json()["id"]
    uid = _seed_user(postgres_engine, tid, user_name="carol")
    r = await mr_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "gremlin"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tenant_scoping_isolated(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    await mr_client.post(
        f"/internal/v1/tenants/{tid_a}/member-roles",
        json={"name": "clinical_lead", "label": "Clinical lead"},
    )
    listed_b = await mr_client.get(f"/internal/v1/tenants/{tid_b}/member-roles")
    assert listed_b.json()["custom"] == []


@pytest.mark.asyncio
async def test_list_404_for_unknown_tenant(mr_client: AsyncClient) -> None:
    r = await mr_client.get(f"/internal/v1/tenants/{uuid.uuid4()}/member-roles")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_404_for_unknown_role(mr_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await mr_client.put(
        f"/internal/v1/tenants/{tid}/member-roles/{uuid.uuid4()}",
        json={"label": "x"},
    )
    assert r.status_code == 404
