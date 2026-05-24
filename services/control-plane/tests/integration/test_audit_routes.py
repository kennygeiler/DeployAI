"""Phase C inc 11.2 — tenant-scoped strategist activity log (integration)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

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
async def a_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "audit-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "audit-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'audit-test')"),
            {"t": str(tid)},
        )
    return tid


def _seed_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    actor_id: uuid.UUID,
    category: str,
    summary: str = "ev",
    created_at: datetime | None = None,
    detail: dict[str, object] | None = None,
) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        if created_at is None:
            conn.execute(
                text(
                    """
                    INSERT INTO strategist_activity_events
                        (id, tenant_id, actor_id, category, summary, detail)
                    VALUES (:i, :t, :a, :c, :s, CAST(:d AS jsonb))
                    """
                ),
                {
                    "i": str(eid),
                    "t": str(tenant_id),
                    "a": str(actor_id),
                    "c": category,
                    "s": summary,
                    "d": json.dumps(detail or {}),
                },
            )
        else:
            conn.execute(
                text(
                    """
                    INSERT INTO strategist_activity_events
                        (id, tenant_id, actor_id, category, summary, detail, created_at)
                    VALUES (:i, :t, :a, :c, :s, CAST(:d AS jsonb), :ts)
                    """
                ),
                {
                    "i": str(eid),
                    "t": str(tenant_id),
                    "a": str(actor_id),
                    "c": category,
                    "s": summary,
                    "d": json.dumps(detail or {}),
                    "ts": created_at,
                },
            )
    return eid


@pytest.mark.asyncio
async def test_requires_internal_key(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "audit-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        tid = _seed_tenant(postgres_engine)
        r = await c.get(f"/internal/v1/audit-events?tenant_id={tid}")
        assert r.status_code == 401
    clear_engine_cache()


@pytest.mark.asyncio
async def test_unknown_tenant_returns_404(a_client: AsyncClient) -> None:
    r = await a_client.get(f"/internal/v1/audit-events?tenant_id={uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_empty_when_no_events(a_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid}")
    assert r.status_code == 200, r.text
    assert r.json() == []


@pytest.mark.asyncio
async def test_tenant_isolation(a_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    actor = uuid.uuid4()
    _seed_event(postgres_engine, tenant_id=tid_a, actor_id=actor, category="override_added")
    _seed_event(postgres_engine, tenant_id=tid_b, actor_id=actor, category="override_added")

    r = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid_a}")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["tenant_id"] == str(tid_a)


@pytest.mark.asyncio
async def test_orders_desc_and_limit(a_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    actor = uuid.uuid4()
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    ids = [
        _seed_event(
            postgres_engine,
            tenant_id=tid,
            actor_id=actor,
            category="override_added",
            summary=f"ev-{i}",
            created_at=base + timedelta(minutes=i),
        )
        for i in range(5)
    ]
    r = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid}&limit=3")
    assert r.status_code == 200
    body = r.json()
    assert [row["id"] for row in body] == [str(ids[4]), str(ids[3]), str(ids[2])]


@pytest.mark.asyncio
async def test_before_cursor_pagination(a_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    actor = uuid.uuid4()
    base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    for i in range(4):
        _seed_event(
            postgres_engine,
            tenant_id=tid,
            actor_id=actor,
            category="override_added",
            summary=f"ev-{i}",
            created_at=base + timedelta(minutes=i),
        )
    first = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid}&limit=2")
    assert first.status_code == 200
    first_body = first.json()
    assert len(first_body) == 2
    cursor = first_body[-1]["created_at"]

    older = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid}&limit=2&before={cursor}")
    assert older.status_code == 200
    older_body = older.json()
    assert len(older_body) == 2
    assert {row["id"] for row in older_body}.isdisjoint({row["id"] for row in first_body})


@pytest.mark.asyncio
async def test_filter_by_actor_and_kind(a_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    actor_a = uuid.uuid4()
    actor_b = uuid.uuid4()
    _seed_event(postgres_engine, tenant_id=tid, actor_id=actor_a, category="override_added")
    _seed_event(postgres_engine, tenant_id=tid, actor_id=actor_a, category="note_added")
    _seed_event(postgres_engine, tenant_id=tid, actor_id=actor_b, category="override_added")

    by_actor = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid}&actor={actor_a}")
    assert by_actor.status_code == 200
    assert {row["actor_id"] for row in by_actor.json()} == {str(actor_a)}

    by_kind = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid}&kind=override_added")
    assert by_kind.status_code == 200
    body = by_kind.json()
    assert len(body) == 2
    assert {row["category"] for row in body} == {"override_added"}

    combo = await a_client.get(
        f"/internal/v1/audit-events?tenant_id={tid}&actor={actor_a}&kind=note_added",
    )
    assert combo.status_code == 200
    combo_body = combo.json()
    assert len(combo_body) == 1
    assert combo_body[0]["actor_id"] == str(actor_a)
    assert combo_body[0]["category"] == "note_added"


@pytest.mark.asyncio
async def test_limit_validation(a_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    too_big = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid}&limit=501")
    assert too_big.status_code == 422
    too_small = await a_client.get(f"/internal/v1/audit-events?tenant_id={tid}&limit=0")
    assert too_small.status_code == 422
