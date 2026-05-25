"""Integration: ledger read routes (Phase F1.c)."""

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
from control_plane.domain.ledger import LedgerEvent, LedgerEventAffects, LedgerEventCause
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest.fixture(autouse=True)
def _ensure_ledger_tables(postgres_engine: Engine) -> Generator[None]:
    """F1.a owns the migration; until it lands, create-if-missing here.

    Idempotent: once F1.a's 0034-0037 migrations exist, `CREATE TABLE IF NOT
    EXISTS` is a no-op against the already-migrated container.
    """
    tables = [
        Base.metadata.tables[LedgerEvent.__tablename__],
        Base.metadata.tables[LedgerEventCause.__tablename__],
        Base.metadata.tables[LedgerEventAffects.__tablename__],
    ]
    Base.metadata.create_all(postgres_engine, tables=tables, checkfirst=True)
    with postgres_engine.begin() as conn:
        conn.execute(text("TRUNCATE ledger_event_causes, ledger_event_affects, ledger_events CASCADE"))
    yield
    with postgres_engine.begin() as conn:
        conn.execute(text("TRUNCATE ledger_event_causes, ledger_event_affects, ledger_events CASCADE"))


@pytest_asyncio.fixture
async def l_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ledger-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "ledger-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'ledger-test')"), {"t": str(tid)})
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
    engagement_id: uuid.UUID | None,
    occurred_at: datetime,
    source_kind: str = "audit_other",
    actor_kind: str = "user",
    actor_id: str | None = None,
    summary: str = "ev",
    detail: dict[str, object] | None = None,
    source_ref: uuid.UUID | None = None,
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
                  (:id, :tid, :eid, :occ, :ak, :aid, :sk, :sr, :sum, CAST(:d AS jsonb))
                """
            ),
            {
                "id": str(eid),
                "tid": str(tenant_id),
                "eid": str(engagement_id) if engagement_id is not None else None,
                "occ": occurred_at,
                "ak": actor_kind,
                "aid": actor_id,
                "sk": source_kind,
                "sr": str(source_ref) if source_ref is not None else None,
                "sum": summary,
                "d": json.dumps(detail or {}),
            },
        )
    return eid


def _link_cause(engine: Engine, *, event_id: uuid.UUID, caused_by_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES (:e, :c)"),
            {"e": str(event_id), "c": str(caused_by_id)},
        )


def _link_affect(engine: Engine, *, event_id: uuid.UUID, kind: str, entity_id: uuid.UUID) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO ledger_event_affects (event_id, entity_kind, entity_id) VALUES (:e, :k, :i)"),
            {"e": str(event_id), "k": kind, "i": str(entity_id)},
        )


@pytest.mark.asyncio
async def test_requires_internal_key(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ledger-test-key")
    clear_engine_cache()
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}")
    assert r.status_code == 401
    clear_engine_cache()


@pytest.mark.asyncio
async def test_unknown_engagement_returns_404(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await l_client.get(f"/internal/v1/engagements/{uuid.uuid4()}/ledger?tenant_id={tid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_tenant_isolation_returns_404_for_other_tenant(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    eng_a = _seed_engagement(postgres_engine, tid_a)
    _seed_event(
        postgres_engine,
        tenant_id=tid_a,
        engagement_id=eng_a,
        occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    r = await l_client.get(f"/internal/v1/engagements/{eng_a}/ledger?tenant_id={tid_b}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_returns_events_chronologically_desc(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    ids = [
        _seed_event(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            occurred_at=base + timedelta(minutes=i),
            summary=f"ev-{i}",
        )
        for i in range(3)
    ]
    r = await l_client.get(f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["next_cursor"] is None
    assert [row["id"] for row in body["events"]] == [str(ids[2]), str(ids[1]), str(ids[0])]


@pytest.mark.asyncio
async def test_cursor_pagination(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    for i in range(5):
        _seed_event(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            occurred_at=base + timedelta(minutes=i),
            summary=f"ev-{i}",
        )
    first = await l_client.get(f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}&limit=2")
    assert first.status_code == 200, first.text
    first_body = first.json()
    assert len(first_body["events"]) == 2
    assert first_body["next_cursor"] is not None

    second = await l_client.get(
        f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}&limit=2&cursor={first_body['next_cursor']}"
    )
    assert second.status_code == 200
    second_body = second.json()
    assert len(second_body["events"]) == 2
    overlap = {r["id"] for r in first_body["events"]} & {r["id"] for r in second_body["events"]}
    assert overlap == set()


@pytest.mark.asyncio
async def test_list_filters(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    actor = str(uuid.uuid4())
    _seed_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=base,
        source_kind="email_ingest",
        actor_id=actor,
    )
    _seed_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=base + timedelta(minutes=1),
        source_kind="meeting_webhook",
        actor_id=actor,
    )
    _seed_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=base + timedelta(minutes=2),
        source_kind="email_ingest",
        actor_id="other",
    )

    by_kind = await l_client.get(f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}&source_kind=email_ingest")
    assert by_kind.status_code == 200
    assert all(r["source_kind"] == "email_ingest" for r in by_kind.json()["events"])

    by_actor = await l_client.get(f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}&actor_id={actor}")
    assert by_actor.status_code == 200
    assert all(r["actor_id"] == actor for r in by_actor.json()["events"])


@pytest.mark.asyncio
async def test_get_event_expands_cause_and_affect(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    base = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    cause = _seed_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=base,
        summary="ingest",
    )
    effect = _seed_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=base + timedelta(minutes=1),
        summary="proposal",
    )
    _link_cause(postgres_engine, event_id=effect, caused_by_id=cause)
    node_id = uuid.uuid4()
    _link_affect(postgres_engine, event_id=effect, kind="matrix_node", entity_id=node_id)

    r = await l_client.get(f"/internal/v1/engagements/{eid}/ledger/{effect}?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == str(effect)
    assert body["caused_by"] == [str(cause)]
    assert body["affects"] == [{"entity_kind": "matrix_node", "entity_id": str(node_id)}]


@pytest.mark.asyncio
async def test_get_event_404_when_in_other_engagement(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eng_a = _seed_engagement(postgres_engine, tid)
    eng_b = _seed_engagement(postgres_engine, tid)
    ev_a = _seed_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eng_a,
        occurred_at=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )
    r = await l_client.get(f"/internal/v1/engagements/{eng_b}/ledger/{ev_a}?tenant_id={tid}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_limit_validation(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    too_big = await l_client.get(f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}&limit=501")
    assert too_big.status_code == 422
    too_small = await l_client.get(f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}&limit=0")
    assert too_small.status_code == 422


@pytest.mark.asyncio
async def test_invalid_cursor_422(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    r = await l_client.get(f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}&cursor=notbase64")
    assert r.status_code == 422
