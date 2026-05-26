"""Integration: ``query_ledger`` + ``walk_chain`` tool happy-path tests."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.tools.ledger import query_ledger, walk_chain
from control_plane.db import clear_engine_cache, get_app_db_session

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def app_session(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    clear_engine_cache()
    try:
        yield None
    finally:
        clear_engine_cache()


@pytest.fixture
def seeded(postgres_engine: Engine) -> Generator[dict[str, uuid.UUID]]:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    with postgres_engine.begin() as c:
        c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'ledger-test')"), {"t": str(tid)})
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'eng', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tid)},
        )
    yield {"tenant_id": tid, "engagement_id": eid}


def _ins_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    occurred_at: datetime,
    source_kind: str = "audit_other",
    actor_id: str | None = None,
    summary: str = "ev",
    detail: dict[str, object] | None = None,
) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO ledger_events
                  (id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id,
                   source_kind, source_ref, summary, detail)
                VALUES
                  (:id, :tid, :eid, :occ, 'user', :aid, :sk, NULL, :sum, CAST(:d AS jsonb))
                """
            ),
            {
                "id": str(eid),
                "tid": str(tenant_id),
                "eid": str(engagement_id),
                "occ": occurred_at,
                "aid": actor_id,
                "sk": source_kind,
                "sum": summary,
                "d": json.dumps(detail or {}),
            },
        )
    return eid


def _link_cause(engine: Engine, *, event_id: uuid.UUID, caused_by_id: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES (:e, :c)"),
            {"e": str(event_id), "c": str(caused_by_id)},
        )


def _count_invocations(engine: Engine, tenant_id: uuid.UUID) -> int:
    with engine.connect() as c:
        return int(
            c.execute(
                text(
                    "SELECT count(*) FROM ledger_events WHERE tenant_id = :t AND source_kind = 'agent_tool_invocation'"
                ),
                {"t": str(tenant_id)},
            ).scalar_one()
        )


@pytest.mark.asyncio
async def test_query_ledger_returns_engagement_events_only(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    a = _ins_event(postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base, summary="alpha")
    b = _ins_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=base + timedelta(minutes=1),
        summary="beta",
    )

    async for session in get_app_db_session():
        result = await query_ledger(session, tenant_id=tid, engagement_id=eid, limit=10)
        await session.commit()
        ids = {r["id"] for r in result.rows}
        assert str(a) in ids
        assert str(b) in ids
        assert result.truncated is False
        assert all(c.kind == "event" for c in result.citations)
        assert len(result.citations) == 2

    assert _count_invocations(postgres_engine, tid) == 1


@pytest.mark.asyncio
async def test_query_ledger_pagination_advances_via_cursor(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    for i in range(5):
        _ins_event(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            occurred_at=base + timedelta(minutes=i),
            summary=f"row-{i}",
        )

    async for session in get_app_db_session():
        first = await query_ledger(session, tenant_id=tid, engagement_id=eid, limit=2)
        assert first.truncated is True
        assert first.next_cursor is not None
        assert len(first.rows) == 2

        second = await query_ledger(session, tenant_id=tid, engagement_id=eid, limit=2, cursor=first.next_cursor)
        await session.commit()
        assert len(second.rows) == 2
        assert {r["id"] for r in first.rows}.isdisjoint({r["id"] for r in second.rows})


@pytest.mark.asyncio
async def test_query_ledger_filters_by_source_kind(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    _ins_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=base,
        source_kind="audit_other",
        summary="aud",
    )
    target = _ins_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=base + timedelta(minutes=1),
        source_kind="manual_capture",
        summary="cap",
    )

    async for session in get_app_db_session():
        result = await query_ledger(session, tenant_id=tid, engagement_id=eid, source_kind="manual_capture", limit=10)
        await session.commit()
        assert [r["id"] for r in result.rows] == [str(target)]


@pytest.mark.asyncio
async def test_walk_chain_upstream_walk(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    a = _ins_event(postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base, summary="a")
    b = _ins_event(
        postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base + timedelta(minutes=1), summary="b"
    )
    c = _ins_event(
        postgres_engine, tenant_id=tid, engagement_id=eid, occurred_at=base + timedelta(minutes=2), summary="c"
    )
    _link_cause(postgres_engine, event_id=b, caused_by_id=a)
    _link_cause(postgres_engine, event_id=c, caused_by_id=b)

    async for session in get_app_db_session():
        result = await walk_chain(
            session,
            tenant_id=tid,
            engagement_id=eid,
            event_id=c,
            direction="upstream",
            max_depth=3,
        )
        await session.commit()
        ids = {r["id"] for r in result.rows}
        assert ids == {str(a), str(b), str(c)}


@pytest.mark.asyncio
async def test_walk_chain_missing_root_returns_empty(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        result = await walk_chain(
            session,
            tenant_id=tid,
            engagement_id=eid,
            event_id=uuid.uuid4(),
        )
        await session.commit()
        assert result.rows == []
        assert result.citations == []
