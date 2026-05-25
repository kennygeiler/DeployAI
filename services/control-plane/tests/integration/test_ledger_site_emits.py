"""End-to-end: every write site we wired in Phase F1.b lands a ledger row
with the expected ``source_kind`` + ``actor_kind``."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from control_plane.db import clear_engine_cache
from control_plane.domain.ledger import LedgerEvent, LedgerEventAffects
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(eng: Engine) -> str:
    return eng.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def session_factory(
    postgres_engine: Engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    eng: AsyncEngine = create_async_engine(_async_url(postgres_engine), future=True)
    try:
        yield async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    finally:
        await eng.dispose()


@pytest_asyncio.fixture
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
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
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'ledger-sites')"),
            {"t": str(tid)},
        )
    return tid


async def _new_engagement(client: AsyncClient, postgres_engine: Engine) -> tuple[uuid.UUID, str]:
    tid = _seed_tenant(postgres_engine)
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "ledger sites"})
    assert r.status_code == 201, r.text
    return tid, r.json()["id"]


async def _ledger_rows(factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID) -> list[LedgerEvent]:
    async with factory() as session:
        r = await session.execute(
            select(LedgerEvent).where(LedgerEvent.tenant_id == tenant_id).order_by(LedgerEvent.recorded_at)
        )
        return list(r.scalars().all())


async def _affects(factory: async_sessionmaker[AsyncSession], event_id: uuid.UUID) -> list[LedgerEventAffects]:
    async with factory() as session:
        r = await session.execute(select(LedgerEventAffects).where(LedgerEventAffects.event_id == event_id))
        return list(r.scalars().all())


_SINGLE_EMAIL = (
    "Message-ID: <ledger-1@deploy.ai>\r\n"
    "From: FDE <fde@deploy.ai>\r\n"
    "To: dev@customer.example\r\n"
    "Subject: Ledger test thread\r\n"
    "Date: Sun, 24 May 2026 15:00:00 +0000\r\n"
    "\r\n"
    "Body goes here.\r\n"
)


@pytest.mark.asyncio
async def test_email_ingest_emits_ledger_row(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await e_client.post(
        f"/internal/v1/emails/ingest?tenant_id={tid}",
        json={"source": "imap_paste", "raw": _SINGLE_EMAIL},
    )
    assert r.status_code == 201, r.text
    email_id = uuid.UUID(r.json()[0]["id"])

    rows = await _ledger_rows(session_factory, tid)
    kinds = [row.source_kind for row in rows]
    assert "email_ingest" in kinds
    email_row = next(row for row in rows if row.source_kind == "email_ingest")
    assert email_row.actor_kind == "system"
    assert email_row.source_ref == email_id
    assert email_row.engagement_id is None
    assert email_row.detail.get("source") == "imap_paste"


@pytest.mark.asyncio
async def test_meeting_webhook_emits_ledger_row(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await e_client.post(
        f"/internal/v1/meetings/webhook?tenant_id={tid}",
        json={
            "source": "manual_paste",
            "payload": {
                "title": "Kickoff call",
                "start_ts": "2026-05-09T15:00:00+00:00",
                "attendees": ["a@x.com"],
            },
        },
    )
    assert r.status_code == 201, r.text
    meeting_id = uuid.UUID(r.json()["id"])

    rows = await _ledger_rows(session_factory, tid)
    kinds = [row.source_kind for row in rows]
    assert "meeting_webhook" in kinds
    m_row = next(row for row in rows if row.source_kind == "meeting_webhook")
    assert m_row.actor_kind == "system"
    assert m_row.source_ref == meeting_id


@pytest.mark.asyncio
async def test_matrix_node_crud_emits_three_ledger_rows(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "system", "title": "LiDAR ingest"},
    )
    assert created.status_code == 201
    node_id = uuid.UUID(created.json()["id"])

    patched = await e_client.patch(
        f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}",
        json={"title": "LiDAR ingest pipeline"},
    )
    assert patched.status_code == 200

    deleted = await e_client.delete(f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}")
    assert deleted.status_code == 204

    rows = await _ledger_rows(session_factory, tid)
    matrix_rows = [row for row in rows if row.source_kind.startswith("matrix_node_")]
    by_kind = {row.source_kind: row for row in matrix_rows}
    assert set(by_kind) == {"matrix_node_created", "matrix_node_updated", "matrix_node_deleted"}
    for kind in ("matrix_node_created", "matrix_node_updated", "matrix_node_deleted"):
        row = by_kind[kind]
        assert row.engagement_id == uuid.UUID(eid)
        assert row.actor_kind == "user"
        assert row.source_ref == node_id

    create_affects = await _affects(session_factory, by_kind["matrix_node_created"].id)
    assert [(a.entity_kind, a.entity_id) for a in create_affects] == [("matrix_node", node_id)]


@pytest.mark.asyncio
async def test_matrix_edge_create_delete_emits_ledger_rows(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)

    async def _node(node_type: str, title: str) -> uuid.UUID:
        r = await e_client.post(
            f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
            json={"node_type": node_type, "title": title},
        )
        return uuid.UUID(r.json()["id"])

    risk_id = await _node("risk", "Calibration slip")
    system_id = await _node("system", "LiDAR ingest")

    created_edge = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}",
        json={"edge_type": "threatens", "from_node_id": str(risk_id), "to_node_id": str(system_id)},
    )
    assert created_edge.status_code == 201
    edge_id = uuid.UUID(created_edge.json()["id"])

    deleted = await e_client.delete(f"/internal/v1/engagements/{eid}/matrix/edges/{edge_id}?tenant_id={tid}")
    assert deleted.status_code == 204

    rows = await _ledger_rows(session_factory, tid)
    edge_kinds = [row.source_kind for row in rows if row.source_kind.startswith("matrix_edge_")]
    assert "matrix_edge_created" in edge_kinds
    assert "matrix_edge_deleted" in edge_kinds


def _seed_event_and_proposal(
    engine: Engine,
    tenant_id: uuid.UUID,
    engagement_id: str,
    proposal_kind: str,
    payload: dict[str, object],
) -> uuid.UUID:
    with engine.begin() as conn:
        event_id = conn.execute(
            text(
                """
                INSERT INTO canonical_memory_events (tenant_id, engagement_id, event_type, occurred_at)
                VALUES (:t, :e, 'ingest.meeting_note', now())
                RETURNING id
                """
            ),
            {"t": str(tenant_id), "e": engagement_id},
        ).scalar_one()
        proposal_id = conn.execute(
            text(
                """
                INSERT INTO matrix_proposals
                  (tenant_id, engagement_id, source_event_id, proposal_kind, payload, rationale)
                VALUES
                  (:t, :e, :ev, :kind, CAST(:payload AS jsonb), :rationale)
                RETURNING id
                """
            ),
            {
                "t": str(tenant_id),
                "e": engagement_id,
                "ev": str(event_id),
                "kind": proposal_kind,
                "payload": json.dumps(payload),
                "rationale": "test fixture",
            },
        ).scalar_one()
    return uuid.UUID(str(proposal_id))


@pytest.mark.asyncio
async def test_proposal_accept_emits_ledger_with_affects(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    proposal_id = _seed_event_and_proposal(
        postgres_engine,
        tid,
        eid,
        "node",
        {"node_type": "system", "title": "Accepted system"},
    )

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/{proposal_id}/accept?tenant_id={tid}",
        json={"actor_id": "tester"},
    )
    assert r.status_code == 200, r.text
    result_node_id = uuid.UUID(r.json()["result_node_id"])

    rows = await _ledger_rows(session_factory, tid)
    accept_row = next(row for row in rows if row.source_kind == "proposal_accepted")
    assert accept_row.actor_kind == "user"
    assert accept_row.actor_id == "tester"
    assert accept_row.source_ref == proposal_id

    affects = await _affects(session_factory, accept_row.id)
    assert ("matrix_node", result_node_id) in [(a.entity_kind, a.entity_id) for a in affects]


@pytest.mark.asyncio
async def test_proposal_reject_emits_ledger(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    proposal_id = _seed_event_and_proposal(
        postgres_engine,
        tid,
        eid,
        "node",
        {"node_type": "risk", "title": "rejected risk"},
    )
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/{proposal_id}/reject?tenant_id={tid}",
        json={"actor_id": "tester"},
    )
    assert r.status_code == 200

    rows = await _ledger_rows(session_factory, tid)
    kinds = [row.source_kind for row in rows]
    assert "proposal_rejected" in kinds


@pytest.mark.asyncio
async def test_insight_dismiss_emits_insight_closed(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    with postgres_engine.begin() as conn:
        insight_id = conn.execute(
            text(
                """
                INSERT INTO matrix_insights
                    (tenant_id, engagement_id, agent, insight_type, severity, title, body, dedup_key)
                VALUES
                    (:t, :e, 'oracle', 'stale_commitment', 'medium', 'stale title', 'body',
                     'oracle:eid:stale_commitment:node')
                RETURNING id
                """
            ),
            {"t": str(tid), "e": eid},
        ).scalar_one()

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/insights/{insight_id}/dismiss?tenant_id={tid}",
        json={"actor_id": "tester"},
    )
    assert r.status_code == 200, r.text

    rows = await _ledger_rows(session_factory, tid)
    closed = next(row for row in rows if row.source_kind == "insight_closed")
    assert closed.actor_kind == "user"
    assert closed.source_ref == uuid.UUID(str(insight_id))
    affects = await _affects(session_factory, closed.id)
    assert ("insight", uuid.UUID(str(insight_id))) in [(a.entity_kind, a.entity_id) for a in affects]
