"""Epic 10 — internal strategist overrides API (integration)."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from control_plane.db import clear_engine_cache
from control_plane.main import app
from control_plane.services.learning_override import record_learning_override

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(conn: Engine, tid: uuid.UUID) -> None:
    with conn.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'epic10') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _sync_seed_learning_with_evidence(postgres_engine: Engine, tid: uuid.UUID) -> tuple[uuid.UUID, uuid.UUID]:
    """Return learning_id and a second evidence event id for override."""
    with postgres_engine.begin() as conn:
        e1 = conn.execute(
            text(
                "INSERT INTO canonical_memory_events (tenant_id, event_type, occurred_at) "
                "VALUES (:t, 'seed', now()) RETURNING id"
            ),
            {"t": tid},
        ).scalar_one()
        e2 = conn.execute(
            text(
                "INSERT INTO canonical_memory_events (tenant_id, event_type, occurred_at) "
                "VALUES (:t, 'seed2', now()) RETURNING id"
            ),
            {"t": tid},
        ).scalar_one()
        lid = conn.execute(
            text(
                "INSERT INTO solidified_learnings (tenant_id, belief, evidence_event_ids, state) "
                "VALUES (:t, 'Pilot belief', ARRAY[CAST(:e1 AS uuid)], 'solidified') RETURNING id"
            ),
            {"t": tid, "e1": e1},
        ).scalar_one()
    return lid, e2


@pytest_asyncio.fixture
async def ov_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ov-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "ov-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_post_override_201_and_lists(
    ov_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    actor = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    lid, e2 = _sync_seed_learning_with_evidence(postgres_engine, tid)

    r = await ov_client.post(
        f"/internal/v1/strategist/overrides?tenant_id={tid}",
        headers={"X-DeployAI-Actor-Id": str(actor)},
        json={
            "learning_id": str(lid),
            "what_changed": "Belief update",
            "why": "Twenty-char justification here!!",
            "evidence_event_ids": [str(e2)],
            "private_annotation": "eyes only",
        },
    )
    assert r.status_code == 201, r.text
    j = r.json()
    assert "override_event_id" in j
    assert j["affected_surfaces"]

    r2 = await ov_client.get(f"/internal/v1/strategist/overrides?tenant_id={tid}")
    assert r2.status_code == 200
    items = r2.json()["items"]
    assert len(items) >= 1

    r3 = await ov_client.get(
        f"/internal/v1/strategist/overrides/{j['override_event_id']}/private-note?tenant_id={tid}",
        headers={"X-DeployAI-Actor-Id": str(actor)},
    )
    assert r3.status_code == 200
    assert r3.json()["plaintext"] == "eyes only"


@pytest.mark.asyncio
async def test_private_note_forbidden_for_successor(
    ov_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    author = uuid.uuid4()
    other = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    lid, e2 = _sync_seed_learning_with_evidence(postgres_engine, tid)

    eng = create_async_engine(_async_url(postgres_engine))
    try:
        async with async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)() as session:
            oid = await record_learning_override(
                session,
                tenant_id=tid,
                user_id=author,
                learning_id=lid,
                override_evidence_event_ids=[e2],
                what_changed="wc",
                why="12345678901234567890",
                private_annotation_plaintext="secret",
            )
    finally:
        await eng.dispose()

    r = await ov_client.get(
        f"/internal/v1/strategist/overrides/{oid}/private-note?tenant_id={tid}",
        headers={
            "X-DeployAI-Actor-Id": str(other),
            "X-DeployAI-Effective-Role": "successor_strategist",
        },
    )
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_personal_audit_lists_posted_activity(
    ov_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    actor = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    for i in range(5):
        r = await ov_client.post(
            "/internal/v1/strategist/activity-events",
            json={
                "tenant_id": str(tid),
                "actor_id": str(actor),
                "category": f"cat_{i}",
                "summary": f"Summary {i}",
                "detail": {"i": i},
            },
        )
        assert r.status_code == 201, r.text

    r2 = await ov_client.get(
        f"/internal/v1/strategist/personal-audit?tenant_id={tid}",
        headers={"X-DeployAI-Actor-Id": str(actor)},
    )
    assert r2.status_code == 200
    assert len(r2.json()["items"]) == 5
