"""Sprint 6 inc 1 — tenant custom matrix node-type registry (integration)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.domain.canonical_memory.node_types import BUILTIN_NODE_TYPES
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def nt_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "nt-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "nt-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'node-types-test')"),
            {"t": str(tid)},
        )
    return tid


@pytest.mark.asyncio
async def test_list_returns_builtins_when_no_custom(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await nt_client.get(f"/internal/v1/tenants/{tid}/node-types")
    assert r.status_code == 200, r.text
    body = r.json()
    assert {b["name"] for b in body["builtin"]} == set(BUILTIN_NODE_TYPES)
    assert body["custom"] == []


@pytest.mark.asyncio
async def test_create_list_update_delete_roundtrip(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    created = await nt_client.post(
        f"/internal/v1/tenants/{tid}/node-types",
        json={
            "name": "patient_journey",
            "label": "Patient journey",
            "color": "#fde68a",
            "description": "A patient's path through a clinical pathway.",
        },
    )
    assert created.status_code == 201, created.text
    row = created.json()
    assert row["name"] == "patient_journey"
    assert row["color"] == "#fde68a"
    nt_id = row["id"]

    listed = await nt_client.get(f"/internal/v1/tenants/{tid}/node-types")
    assert listed.status_code == 200
    assert [c["name"] for c in listed.json()["custom"]] == ["patient_journey"]

    updated = await nt_client.put(
        f"/internal/v1/tenants/{tid}/node-types/{nt_id}",
        json={"label": "Care journey", "color": "#bfdbfe", "description": None},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["label"] == "Care journey"
    assert body["color"] == "#bfdbfe"
    assert body["description"] is None
    assert body["name"] == "patient_journey"

    deleted = await nt_client.delete(f"/internal/v1/tenants/{tid}/node-types/{nt_id}")
    assert deleted.status_code == 204
    listed2 = await nt_client.get(f"/internal/v1/tenants/{tid}/node-types")
    assert listed2.json()["custom"] == []


@pytest.mark.asyncio
async def test_create_rejects_builtin_collision(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await nt_client.post(
        f"/internal/v1/tenants/{tid}/node-types",
        json={"name": "stakeholder", "label": "Custom stakeholder"},
    )
    assert r.status_code == 422
    assert "built-in" in r.text


@pytest.mark.asyncio
async def test_create_rejects_malformed_name(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    for bad in ("Patient_Journey", "1abc", "with-dash", "x" * 60, ""):
        r = await nt_client.post(
            f"/internal/v1/tenants/{tid}/node-types",
            json={"name": bad, "label": "x"},
        )
        assert r.status_code == 422, f"expected 422 for {bad!r}, got {r.status_code}"


@pytest.mark.asyncio
async def test_create_rejects_malformed_color(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await nt_client.post(
        f"/internal/v1/tenants/{tid}/node-types",
        json={"name": "patient_journey", "label": "PJ", "color": "red"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_create_409_on_duplicate_name(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    await nt_client.post(
        f"/internal/v1/tenants/{tid}/node-types",
        json={"name": "feature_flag", "label": "Feature flag"},
    )
    dup = await nt_client.post(
        f"/internal/v1/tenants/{tid}/node-types",
        json={"name": "feature_flag", "label": "Other"},
    )
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_delete_in_use_returns_409(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    nt_resp = await nt_client.post(
        f"/internal/v1/tenants/{tid}/node-types",
        json={"name": "patient_journey", "label": "Patient journey"},
    )
    nt_id = nt_resp.json()["id"]
    e_resp = await nt_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Clinic A"},
    )
    eid = e_resp.json()["id"]
    node_resp = await nt_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "patient_journey", "title": "Surgery prep"},
    )
    assert node_resp.status_code == 201, node_resp.text

    blocked = await nt_client.delete(f"/internal/v1/tenants/{tid}/node-types/{nt_id}")
    assert blocked.status_code == 409
    assert "in use" in blocked.text


@pytest.mark.asyncio
async def test_matrix_node_create_accepts_custom_type(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    await nt_client.post(
        f"/internal/v1/tenants/{tid}/node-types",
        json={"name": "feature_flag", "label": "Feature flag"},
    )
    e_resp = await nt_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "SaaS one"},
    )
    eid = e_resp.json()["id"]
    r = await nt_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "feature_flag", "title": "kill-switch-v2"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["node_type"] == "feature_flag"


@pytest.mark.asyncio
async def test_matrix_node_create_still_rejects_unknown_type(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    e_resp = await nt_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Eng"},
    )
    eid = e_resp.json()["id"]
    r = await nt_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "gremlin", "title": "no"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tenant_scoping_isolated(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    await nt_client.post(
        f"/internal/v1/tenants/{tid_a}/node-types",
        json={"name": "patient_journey", "label": "Patient journey"},
    )
    listed_b = await nt_client.get(f"/internal/v1/tenants/{tid_b}/node-types")
    assert listed_b.json()["custom"] == []


@pytest.mark.asyncio
async def test_list_404_for_unknown_tenant(nt_client: AsyncClient) -> None:
    r = await nt_client.get(f"/internal/v1/tenants/{uuid.uuid4()}/node-types")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_404_for_unknown_node_type(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await nt_client.put(
        f"/internal/v1/tenants/{tid}/node-types/{uuid.uuid4()}",
        json={"label": "x"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_update_rejects_malformed_color(nt_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    created = await nt_client.post(
        f"/internal/v1/tenants/{tid}/node-types",
        json={"name": "patient_journey", "label": "PJ"},
    )
    nt_id = created.json()["id"]
    r = await nt_client.put(
        f"/internal/v1/tenants/{tid}/node-types/{nt_id}",
        json={"color": "not-hex"},
    )
    assert r.status_code == 422
