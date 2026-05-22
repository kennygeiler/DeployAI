"""Engagements internal API (integration) — Phase 1."""

from __future__ import annotations

import uuid

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


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'engagements') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_user(engine: Engine, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_users (id, tenant_id, user_name) VALUES (:u, :t, 'member')"),
            {"u": str(user_id), "t": str(tenant_id)},
        )


@pytest_asyncio.fixture
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "e-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "e-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_create_list_get_engagement(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "NYC DOT LiDAR", "customer_account": "NYC DOT"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "NYC DOT LiDAR"
    assert created["customer_account"] == "NYC DOT"
    assert created["current_phase"] == "P1_pre_engagement"
    assert created["status"] == "active"
    eid = created["id"]

    r2 = await e_client.get(f"/internal/v1/engagements?tenant_id={tid}")
    assert r2.status_code == 200
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0]["id"] == eid

    r3 = await e_client.get(f"/internal/v1/engagements/{eid}?tenant_id={tid}")
    assert r3.status_code == 200
    assert r3.json()["id"] == eid


@pytest.mark.asyncio
async def test_engagement_unknown_tenant_404(e_client: AsyncClient) -> None:
    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={uuid.uuid4()}",
        json={"name": "ghost"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_engagement_invalid_phase_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "bad phase", "current_phase": "P9_nope"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_engagement_tenant_isolation(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """An engagement created under tenant A is not visible to tenant B."""
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a)
    _ins_tenant(postgres_engine, tid_b)

    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid_a}",
        json={"name": "tenant A only"},
    )
    assert r.status_code == 201
    eid = r.json()["id"]

    r_list = await e_client.get(f"/internal/v1/engagements?tenant_id={tid_b}")
    assert r_list.status_code == 200
    assert r_list.json() == []

    r_get = await e_client.get(f"/internal/v1/engagements/{eid}?tenant_id={tid_b}")
    assert r_get.status_code == 404


@pytest.mark.asyncio
async def test_engagement_member_crud(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    _ins_user(postgres_engine, uid, tid)

    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "NYC DOT"})
    assert r.status_code == 201
    eid = r.json()["id"]

    rm = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "fde"},
    )
    assert rm.status_code == 201, rm.text
    member = rm.json()
    assert member["role"] == "fde"
    assert member["user_id"] == str(uid)
    mid = member["id"]

    rl = await e_client.get(f"/internal/v1/engagements/{eid}/members?tenant_id={tid}")
    assert rl.status_code == 200
    assert len(rl.json()) == 1

    rdup = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "biz_dev"},
    )
    assert rdup.status_code == 409

    rdel = await e_client.delete(f"/internal/v1/engagements/{eid}/members/{mid}?tenant_id={tid}")
    assert rdel.status_code == 204

    rl2 = await e_client.get(f"/internal/v1/engagements/{eid}/members?tenant_id={tid}")
    assert rl2.json() == []


@pytest.mark.asyncio
async def test_engagement_member_invalid_role_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    _ins_user(postgres_engine, uid, tid)
    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "x"})
    eid = r.json()["id"]
    rm = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "platform_admin"},
    )
    assert rm.status_code == 422


@pytest.mark.asyncio
async def test_engagement_log_crud(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "NYC DOT"})
    eid = r.json()["id"]

    rl = await e_client.post(
        f"/internal/v1/engagements/{eid}/log?tenant_id={tid}",
        json={
            "entry_kind": "decision",
            "body": "Calibration scheduled for week 3.",
            "author": "fde-1",
            "author_role": "fde",
        },
    )
    assert rl.status_code == 201, rl.text
    entry = rl.json()
    assert entry["entry_kind"] == "decision"
    assert entry["body"] == "Calibration scheduled for week 3."
    assert entry["author"] == "fde-1"
    assert entry["author_role"] == "fde"

    rlist = await e_client.get(f"/internal/v1/engagements/{eid}/log?tenant_id={tid}")
    assert rlist.status_code == 200
    assert len(rlist.json()) == 1


@pytest.mark.asyncio
async def test_engagement_log_invalid_kind_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "x"})
    eid = r.json()["id"]
    rl = await e_client.post(
        f"/internal/v1/engagements/{eid}/log?tenant_id={tid}",
        json={"entry_kind": "rumor", "body": "not a valid kind"},
    )
    assert rl.status_code == 422


async def _new_engagement(e_client: AsyncClient, postgres_engine: Engine) -> tuple[uuid.UUID, str]:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Matrix"})
    return tid, r.json()["id"]


@pytest.mark.asyncio
async def test_matrix_node_crud(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)

    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "system", "title": "LiDAR ingest"},
    )
    assert created.status_code == 201, created.text
    node = created.json()
    assert node["node_type"] == "system"
    assert node["attributes"] == {}
    assert node["evidence_event_ids"] == []
    node_id = node["id"]

    got = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}")
    assert got.status_code == 200
    assert got.json()["title"] == "LiDAR ingest"

    listed = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    patched = await e_client.patch(
        f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}",
        json={"title": "LiDAR ingest pipeline", "status": "at_risk", "attributes": {"owner": "DOT"}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "LiDAR ingest pipeline"
    assert patched.json()["status"] == "at_risk"
    assert patched.json()["attributes"] == {"owner": "DOT"}

    deleted = await e_client.delete(f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}")
    assert deleted.status_code == 204
    missing = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_matrix_node_invalid_type_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "gremlin", "title": "not a valid type"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_matrix_edge_crud(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)

    async def _node(node_type: str, title: str) -> str:
        r = await e_client.post(
            f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
            json={"node_type": node_type, "title": title},
        )
        return str(r.json()["id"])

    risk_id = await _node("risk", "Calibration slip")
    system_id = await _node("system", "LiDAR ingest")

    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}",
        json={"edge_type": "threatens", "from_node_id": risk_id, "to_node_id": system_id},
    )
    assert created.status_code == 201, created.text
    assert created.json()["edge_type"] == "threatens"

    listed = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await e_client.delete(
        f"/internal/v1/engagements/{eid}/matrix/edges/{created.json()['id']}?tenant_id={tid}"
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_matrix_edge_unknown_node_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "system", "title": "only node"},
    )
    node_id = created.json()["id"]
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}",
        json={"edge_type": "depends_on", "from_node_id": node_id, "to_node_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422
