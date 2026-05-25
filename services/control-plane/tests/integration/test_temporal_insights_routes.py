"""Integration: temporal-insights routes (Phase F1.c)."""

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
async def t_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ti-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "ti-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'ti-test')"), {"t": str(tid)})
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
    engagement_id: uuid.UUID | None,
    kind: str,
    severity: str,
    status: str = "open",
    title: str = "title",
    narrative: str = "narrative",
    metrics: dict[str, object] | None = None,
) -> uuid.UUID:
    iid = uuid.uuid4()
    window_start = datetime(2026, 5, 1, tzinfo=UTC)
    window_end = window_start + timedelta(days=7)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO temporal_insights
                  (id, tenant_id, engagement_id, insight_kind, severity, title,
                   narrative, window_start, window_end, evidence_event_ids,
                   metrics, status)
                VALUES
                  (:id, :t, :e, :k, :sev, :ti, :na, :ws, :we,
                   ARRAY[]::uuid[], CAST(:m AS jsonb), :st)
                """
            ),
            {
                "id": str(iid),
                "t": str(tenant_id),
                "e": str(engagement_id) if engagement_id is not None else None,
                "k": kind,
                "sev": severity,
                "ti": title,
                "na": narrative,
                "ws": window_start,
                "we": window_end,
                "m": json.dumps(metrics or {}),
                "st": status,
            },
        )
    return iid


@pytest.mark.asyncio
async def test_requires_internal_key(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ti-test-key")
    clear_engine_cache()
    tid = _seed_tenant(postgres_engine)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get(f"/internal/v1/temporal-insights?tenant_id={tid}")
    assert r.status_code == 401
    clear_engine_cache()


@pytest.mark.asyncio
async def test_unknown_tenant_returns_404(t_client: AsyncClient) -> None:
    r = await t_client.get(f"/internal/v1/temporal-insights?tenant_id={uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_list_filter_by_kind_severity_status(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    _seed_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="stakeholder_churn",
        severity="high",
    )
    _seed_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="stakeholder_churn",
        severity="low",
        status="dismissed",
    )
    _seed_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="risk_open_rate",
        severity="medium",
    )

    all_open = await t_client.get(f"/internal/v1/temporal-insights?tenant_id={tid}&status=open")
    assert all_open.status_code == 200, all_open.text
    assert len(all_open.json()) == 2

    high_only = await t_client.get(f"/internal/v1/temporal-insights?tenant_id={tid}&severity_at_least=high")
    assert high_only.status_code == 200
    assert len(high_only.json()) == 1
    assert high_only.json()[0]["severity"] == "high"

    by_kind = await t_client.get(f"/internal/v1/temporal-insights?tenant_id={tid}&kind=risk_open_rate")
    assert by_kind.status_code == 200
    assert len(by_kind.json()) == 1
    assert by_kind.json()[0]["insight_kind"] == "risk_open_rate"


@pytest.mark.asyncio
async def test_tenant_isolation(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    eng_a = _seed_engagement(postgres_engine, tid_a)
    _seed_insight(
        postgres_engine,
        tenant_id=tid_a,
        engagement_id=eng_a,
        kind="stakeholder_churn",
        severity="medium",
    )
    r = await t_client.get(f"/internal/v1/temporal-insights?tenant_id={tid_b}")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_patch_acknowledge(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    iid = _seed_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="stakeholder_churn",
        severity="medium",
    )
    actor = uuid.uuid4()
    r = await t_client.patch(
        f"/internal/v1/temporal-insights/{iid}?tenant_id={tid}",
        json={"status": "acknowledged", "acknowledged_by": str(actor)},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "acknowledged"
    assert body["acknowledged_by"] == str(actor)
    assert body["acknowledged_at"] is not None


@pytest.mark.asyncio
async def test_patch_dismiss_and_resolve(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    iid = _seed_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="risk_open_rate",
        severity="medium",
    )
    dismissed = await t_client.patch(
        f"/internal/v1/temporal-insights/{iid}?tenant_id={tid}", json={"status": "dismissed"}
    )
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"

    resolved = await t_client.patch(
        f"/internal/v1/temporal-insights/{iid}?tenant_id={tid}", json={"status": "resolved"}
    )
    assert resolved.status_code == 200
    assert resolved.json()["status"] == "resolved"


@pytest.mark.asyncio
async def test_patch_invalid_status_422(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    iid = _seed_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="risk_open_rate",
        severity="medium",
    )
    r = await t_client.patch(f"/internal/v1/temporal-insights/{iid}?tenant_id={tid}", json={"status": "wat"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_unknown_insight_returns_404(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await t_client.patch(
        f"/internal/v1/temporal-insights/{uuid.uuid4()}?tenant_id={tid}",
        json={"status": "dismissed"},
    )
    assert r.status_code == 404
