"""Integration: POST /internal/v1/intelligence/run (Phase F1.c)."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.domain.base import Base
from control_plane.domain.ledger import (
    LedgerEvent,
    LedgerEventAffects,
    LedgerEventCause,
    TemporalInsight,
)
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest.fixture(autouse=True)
def _ensure_ledger_tables(postgres_engine: Engine) -> Generator[None]:
    tables = [
        Base.metadata.tables[LedgerEvent.__tablename__],
        Base.metadata.tables[LedgerEventCause.__tablename__],
        Base.metadata.tables[LedgerEventAffects.__tablename__],
        Base.metadata.tables[TemporalInsight.__tablename__],
    ]
    Base.metadata.create_all(postgres_engine, tables=tables, checkfirst=True)
    with postgres_engine.begin() as conn:
        conn.execute(
            text("TRUNCATE temporal_insights, ledger_event_causes, ledger_event_affects, ledger_events CASCADE")
        )
    yield
    with postgres_engine.begin() as conn:
        conn.execute(
            text("TRUNCATE temporal_insights, ledger_event_causes, ledger_event_affects, ledger_events CASCADE")
        )


@pytest_asyncio.fixture
async def s_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "sched-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "sched-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'sched-test')"), {"t": str(tid)})
    return tid


def _seed_engagement(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'eng', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tenant_id)},
        )
    return eid


def _seed_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    occurred_at: datetime,
    source_kind: str,
    detail: dict[str, object] | None = None,
) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO ledger_events
                  (id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id,
                   source_kind, source_ref, summary, detail)
                VALUES
                  (:id, :tid, :eid, :occ, 'system', NULL, :sk, NULL, 'ev', CAST(:d AS jsonb))
                """
            ),
            {
                "id": str(eid),
                "tid": str(tenant_id),
                "eid": str(engagement_id),
                "occ": occurred_at,
                "sk": source_kind,
                "d": json.dumps(detail or {}),
            },
        )
    return eid


@pytest.mark.asyncio
async def test_run_writes_insight_for_silent_engagement(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    r = await s_client.post(
        f"/internal/v1/intelligence/run?tenant_id={tid}",
        json={"engagement_id": str(eid), "analyzer_kinds": ["engagement_silence"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["insights_written"] == 1

    insights = await s_client.get(f"/internal/v1/temporal-insights?tenant_id={tid}")
    assert insights.status_code == 200
    rows = insights.json()
    assert len(rows) == 1
    assert rows[0]["insight_kind"] == "engagement_silence"
    assert rows[0]["severity"] == "info"


@pytest.mark.asyncio
async def test_run_is_idempotent_for_same_window(postgres_engine: Engine) -> None:
    """Deterministic insight id: same (kind, engagement, window) → upsert single row."""
    from control_plane.db import clear_engine_cache, get_app_db_session
    from control_plane.intelligence.scheduler import run_analyzers

    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    monkey_url = postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    import os

    os.environ["DATABASE_URL"] = monkey_url
    clear_engine_cache()
    moment = datetime(2026, 5, 20, 12, tzinfo=UTC)
    async for session in get_app_db_session():
        first = await run_analyzers(
            session,
            tenant_id=tid,
            engagement_id=eid,
            analyzer_kinds=["engagement_silence"],
            now=moment,
        )
        await session.commit()
        second = await run_analyzers(
            session,
            tenant_id=tid,
            engagement_id=eid,
            analyzer_kinds=["engagement_silence"],
            now=moment,
        )
        await session.commit()
        assert len(first) == 1
        assert len(second) == 1
        assert first[0].id == second[0].id
        break
    clear_engine_cache()


@pytest.mark.asyncio
async def test_run_unknown_analyzer_returns_422(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    r = await s_client.post(
        f"/internal/v1/intelligence/run?tenant_id={tid}",
        json={"engagement_id": str(eid), "analyzer_kinds": ["does_not_exist"]},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_run_unknown_engagement_returns_404(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await s_client.post(
        f"/internal/v1/intelligence/run?tenant_id={tid}",
        json={"engagement_id": str(uuid.uuid4())},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_run_writes_risk_open_rate_when_threshold_exceeded(
    s_client: AsyncClient, postgres_engine: Engine
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    base = datetime.now(UTC) - timedelta(days=3)
    for i in range(10):
        _seed_event(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            occurred_at=base + timedelta(minutes=i),
            source_kind="insight_opened",
            detail={"node_type": "risk", "i": i},
        )
    r = await s_client.post(
        f"/internal/v1/intelligence/run?tenant_id={tid}",
        json={"engagement_id": str(eid), "analyzer_kinds": ["risk_open_rate"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["insights_written"] == 1
