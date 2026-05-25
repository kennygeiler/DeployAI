"""Integration: matrix snapshot read endpoint (Phase F3.b)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

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
async def snapshot_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "snapshot-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "snapshot-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine, label: str = "snapshot-route") -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"), {"t": str(tid), "n": label})
    return tid


def _seed_engagement(engine: Engine, tenant_id: uuid.UUID, *, name: str = "eng") -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, :n, 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tenant_id), "n": name},
        )
    return eid


def _seed_snapshot(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    captured_at: datetime,
    node_titles: tuple[str, ...] = (),
) -> uuid.UUID:
    sid = uuid.uuid4()
    nodes = [{"id": str(uuid.uuid4()), "title": t, "node_type": "stakeholder"} for t in node_titles]
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO matrix_snapshots "
                "  (id, tenant_id, engagement_id, captured_at, nodes, edges, node_count, edge_count) "
                "VALUES (:i, :t, :e, :c, CAST(:n AS jsonb), CAST('[]' AS jsonb), :nc, 0)"
            ),
            {
                "i": str(sid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "c": captured_at,
                "n": json.dumps(nodes),
                "nc": len(nodes),
            },
        )
    return sid


@pytest.mark.asyncio
async def test_exact_date_match_returns_snapshot(snapshot_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    captured = datetime(2026, 6, 15, 0, 0, tzinfo=UTC)
    _seed_snapshot(postgres_engine, tenant_id=tid, engagement_id=eid, captured_at=captured, node_titles=("Alice",))

    r = await snapshot_client.get(f"/internal/v1/engagements/{eid}/matrix-snapshot?tenant_id={tid}&at=2026-06-15")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["captured_at"].startswith("2026-06-15")
    assert len(body["nodes"]) == 1
    assert body["nodes"][0]["title"] == "Alice"
    assert body["edges"] == []


@pytest.mark.asyncio
async def test_nearest_prior_when_no_exact_match(snapshot_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    _seed_snapshot(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        captured_at=datetime(2026, 6, 10, 0, 0, tzinfo=UTC),
        node_titles=("Old",),
    )
    _seed_snapshot(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        captured_at=datetime(2026, 6, 13, 0, 0, tzinfo=UTC),
        node_titles=("Mid",),
    )
    _seed_snapshot(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        captured_at=datetime(2026, 6, 20, 0, 0, tzinfo=UTC),
        node_titles=("Future",),
    )

    r = await snapshot_client.get(f"/internal/v1/engagements/{eid}/matrix-snapshot?tenant_id={tid}&at=2026-06-15")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["captured_at"].startswith("2026-06-13")
    assert body["nodes"][0]["title"] == "Mid"


@pytest.mark.asyncio
async def test_404_when_no_prior_snapshot(snapshot_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    _seed_snapshot(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        captured_at=datetime(2026, 6, 20, 0, 0, tzinfo=UTC),
        node_titles=("Future",),
    )

    r = await snapshot_client.get(f"/internal/v1/engagements/{eid}/matrix-snapshot?tenant_id={tid}&at=2026-06-15")
    assert r.status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["garbage", "2026/06/15", "2026-06-15T12:00:00Z", ""])
async def test_422_on_malformed_at(snapshot_client: AsyncClient, postgres_engine: Engine, bad: str) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)

    r = await snapshot_client.get(f"/internal/v1/engagements/{eid}/matrix-snapshot?tenant_id={tid}&at={bad}")
    assert r.status_code == 422, r.text


@pytest.mark.asyncio
async def test_cross_tenant_returns_404(snapshot_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine, label="tenant-a")
    tid_b = _seed_tenant(postgres_engine, label="tenant-b")
    eid_a = _seed_engagement(postgres_engine, tid_a, name="a-eng")
    _seed_snapshot(
        postgres_engine,
        tenant_id=tid_a,
        engagement_id=eid_a,
        captured_at=datetime(2026, 6, 15, 0, 0, tzinfo=UTC),
        node_titles=("secret",),
    )

    r = await snapshot_client.get(f"/internal/v1/engagements/{eid_a}/matrix-snapshot?tenant_id={tid_b}&at=2026-06-15")
    assert r.status_code == 404
