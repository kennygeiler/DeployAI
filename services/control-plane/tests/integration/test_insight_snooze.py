"""Integration: G4.b — temporal insight snooze + followup quick-actions."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from alembic.config import Config
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from alembic import command
from control_plane.db import clear_engine_cache
from control_plane.main import app

_SERVICE_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def s_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "snooze-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "snooze-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'snooze-test')"),
            {"t": str(tid)},
        )
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


def _seed_insight(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    kind: str = "stakeholder_churn",
    severity: str = "medium",
    status: str = "open",
    snoozed_until: datetime | None = None,
    evidence_event_ids: list[uuid.UUID] | None = None,
) -> uuid.UUID:
    iid = uuid.uuid4()
    window_start = datetime(2026, 5, 1, tzinfo=UTC)
    window_end = window_start + timedelta(days=7)
    evidence_arr = "ARRAY[]::uuid[]"
    params: dict[str, object] = {
        "id": str(iid),
        "t": str(tenant_id),
        "e": str(engagement_id),
        "k": kind,
        "sev": severity,
        "ti": "Title",
        "na": "Narrative",
        "ws": window_start,
        "we": window_end,
        "m": json.dumps({}),
        "st": status,
        "su": snoozed_until,
    }
    if evidence_event_ids:
        evidence_arr = "CAST(:ev AS uuid[])"
        params["ev"] = [str(x) for x in evidence_event_ids]
    sql = f"""
        INSERT INTO temporal_insights
          (id, tenant_id, engagement_id, insight_kind, severity, title,
           narrative, window_start, window_end, evidence_event_ids,
           metrics, status, snoozed_until)
        VALUES
          (:id, :t, :e, :k, :sev, :ti, :na, :ws, :we,
           {evidence_arr}, CAST(:m AS jsonb), :st, :su)
    """
    with engine.begin() as conn:
        conn.execute(text(sql), params)
    return iid


def _seed_ledger_event(engine: Engine, *, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> uuid.UUID:
    eid = uuid.uuid4()
    now = datetime.now(UTC)
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, "
                "source_kind, summary, detail) "
                "VALUES (:i, :t, :e, :o, 'user', 'email_ingest', 'seed', "
                "CAST('{}' AS jsonb))"
            ),
            {"i": str(eid), "t": str(tenant_id), "e": str(engagement_id), "o": now},
        )
    return eid


@pytest.mark.asyncio
async def test_snooze_sets_status_and_snoozed_until(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    iid = _seed_insight(postgres_engine, tenant_id=tid, engagement_id=eid)
    before = datetime.now(UTC)
    r = await s_client.post(
        f"/internal/v1/engagements/{eid}/insights/{iid}/snooze?tenant_id={tid}",
        json={"days": 7},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "snoozed"
    snoozed_until = datetime.fromisoformat(body["snoozed_until"].replace("Z", "+00:00"))
    expected_min = before + timedelta(days=7, seconds=-5)
    expected_max = datetime.now(UTC) + timedelta(days=7, seconds=5)
    assert expected_min <= snoozed_until <= expected_max

    list_r = await s_client.get(f"/internal/v1/temporal-insights?tenant_id={tid}&engagement_id={eid}")
    assert list_r.status_code == 200
    assert [i["id"] for i in list_r.json()] == []


@pytest.mark.asyncio
async def test_snoozed_until_in_past_reappears_in_default_list(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    past = datetime.now(UTC) - timedelta(days=1)
    iid = _seed_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        status="snoozed",
        snoozed_until=past,
    )
    r = await s_client.get(f"/internal/v1/temporal-insights?tenant_id={tid}&engagement_id={eid}")
    assert r.status_code == 200
    ids = [i["id"] for i in r.json()]
    assert str(iid) in ids


@pytest.mark.asyncio
async def test_snooze_invalid_days_returns_422(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    iid = _seed_insight(postgres_engine, tenant_id=tid, engagement_id=eid)
    r = await s_client.post(
        f"/internal/v1/engagements/{eid}/insights/{iid}/snooze?tenant_id={tid}",
        json={"days": 0},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_snooze_cross_tenant_404(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    eid_a = _seed_engagement(postgres_engine, tid_a)
    iid = _seed_insight(postgres_engine, tenant_id=tid_a, engagement_id=eid_a)
    r = await s_client.post(
        f"/internal/v1/engagements/{eid_a}/insights/{iid}/snooze?tenant_id={tid_b}",
        json={"days": 3},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_snooze_emits_ledger_event(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    iid = _seed_insight(postgres_engine, tenant_id=tid, engagement_id=eid)
    r = await s_client.post(
        f"/internal/v1/engagements/{eid}/insights/{iid}/snooze?tenant_id={tid}",
        json={"days": 14},
    )
    assert r.status_code == 200, r.text
    with postgres_engine.begin() as conn:
        rows = conn.execute(
            text("SELECT id, summary FROM ledger_events WHERE tenant_id = :t AND source_kind = 'insight_snoozed'"),
            {"t": str(tid)},
        ).all()
    assert len(rows) == 1
    event_id = rows[0][0]
    with postgres_engine.begin() as conn:
        affects = conn.execute(
            text("SELECT entity_kind, entity_id FROM ledger_event_affects WHERE event_id = :e"),
            {"e": str(event_id)},
        ).all()
    assert (affects[0][0], str(affects[0][1])) == ("insight", str(iid))


@pytest.mark.asyncio
async def test_followup_creates_queue_row_and_ledger(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    seed_ev = _seed_ledger_event(postgres_engine, tenant_id=tid, engagement_id=eid)
    iid = _seed_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        evidence_event_ids=[seed_ev],
    )
    owner = uuid.uuid4()
    due = "2026-06-30"
    r = await s_client.post(
        f"/internal/v1/engagements/{eid}/insights/{iid}/followup?tenant_id={tid}",
        json={"owner_user_id": str(owner), "due_date": due},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    item_id = body["action_queue_item_id"]
    assert item_id.startswith("fu-")

    with postgres_engine.begin() as conn:
        queue_rows = conn.execute(
            text(
                "SELECT id, claimed_by, source, evidence_event_ids "
                "FROM strategist_action_queue_items WHERE id = :i AND tenant_id = :t"
            ),
            {"i": item_id, "t": str(tid)},
        ).all()
    assert len(queue_rows) == 1
    row = queue_rows[0]
    assert row[1] == str(owner)
    assert row[2] == f"insight:{iid}"
    payload = row[3]
    assert payload["linked_insight_id"] == str(iid)
    assert payload["due_date"] == due

    with postgres_engine.begin() as conn:
        ev_rows = conn.execute(
            text("SELECT id FROM ledger_events WHERE tenant_id = :t AND source_kind = 'followup_task_created'"),
            {"t": str(tid)},
        ).all()
    assert len(ev_rows) == 1
    event_id = ev_rows[0][0]
    with postgres_engine.begin() as conn:
        causes = conn.execute(
            text("SELECT caused_by_id FROM ledger_event_causes WHERE event_id = :e"),
            {"e": str(event_id)},
        ).all()
        affects = conn.execute(
            text("SELECT entity_kind, entity_id FROM ledger_event_affects WHERE event_id = :e"),
            {"e": str(event_id)},
        ).all()
    assert [str(c[0]) for c in causes] == [str(seed_ev)]
    assert (affects[0][0], str(affects[0][1])) == ("insight", str(iid))


@pytest.mark.asyncio
async def test_followup_cross_tenant_404(s_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    eid_a = _seed_engagement(postgres_engine, tid_a)
    iid = _seed_insight(postgres_engine, tenant_id=tid_a, engagement_id=eid_a)
    r = await s_client.post(
        f"/internal/v1/engagements/{eid_a}/insights/{iid}/followup?tenant_id={tid_b}",
        json={"owner_user_id": str(uuid.uuid4()), "due_date": "2026-06-30"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_migration_round_trip_clean(postgres_engine: Engine) -> None:
    """0041 upgrade + downgrade must round-trip without leaving artifacts."""
    cfg = Config(str(_SERVICE_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_SERVICE_ROOT / "alembic"))
    cfg.set_main_option(
        "sqlalchemy.url",
        postgres_engine.url.render_as_string(hide_password=False),
    )

    with postgres_engine.begin() as conn:
        before = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'temporal_insights' AND column_name = 'snoozed_until'"
            )
        ).all()
    assert len(before) == 1

    command.downgrade(cfg, "20260613_0040")
    with postgres_engine.begin() as conn:
        after_down = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'temporal_insights' AND column_name = 'snoozed_until'"
            )
        ).all()
    assert after_down == []

    command.upgrade(cfg, "head")
    with postgres_engine.begin() as conn:
        after_up = conn.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'temporal_insights' AND column_name = 'snoozed_until'"
            )
        ).all()
    assert len(after_up) == 1
