"""Audit-decision internal route (G2.c) — integration tests."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator

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


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'audit-dec') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _seed_event_and_proposal(
    engine: Engine,
    tenant_id: uuid.UUID,
    engagement_id: str,
    payload: dict[str, object],
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert canonical event + pending proposal + matching llm_proposal_created
    ledger row. Return (event_id, proposal_id)."""
    with engine.begin() as conn:
        canonical_event_id = conn.execute(
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
                  (:t, :e, :ev, 'node', CAST(:payload AS jsonb), 'audit-decision test')
                RETURNING id
                """
            ),
            {
                "t": str(tenant_id),
                "e": engagement_id,
                "ev": str(canonical_event_id),
                "payload": json.dumps(payload),
            },
        ).scalar_one()
        ledger_event_id = conn.execute(
            text(
                """
                INSERT INTO ledger_events
                  (tenant_id, engagement_id, occurred_at, actor_kind, actor_id,
                   source_kind, source_ref, summary, detail)
                VALUES
                  (:t, :e, now(), 'agent:matrix_extractor', 'cartographer',
                   'llm_proposal_created', :ref, 'proposal drafted: node',
                   CAST('{}' AS jsonb))
                RETURNING id
                """
            ),
            {"t": str(tenant_id), "e": engagement_id, "ref": str(proposal_id)},
        ).scalar_one()
    return ledger_event_id, proposal_id


@pytest_asyncio.fixture
async def ad_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ad-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "ad-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


async def _new_engagement(client: AsyncClient, postgres_engine: Engine) -> tuple[uuid.UUID, str]:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "audit-dec"})
    assert r.status_code == 201, r.text
    return tid, r.json()["id"]


@pytest.mark.asyncio
async def test_audit_decision_marks_proposal_and_emits_ledger(ad_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ad_client, postgres_engine)
    event_id, proposal_id = _seed_event_and_proposal(
        postgres_engine, tid, eid, {"node_type": "risk", "title": "Bad inference"}
    )

    r = await ad_client.post(
        f"/internal/v1/engagements/{eid}/audit-decision?tenant_id={tid}",
        json={"event_id": str(event_id), "reason": "wrong entity type"},
    )
    assert r.status_code == 200, r.text
    proposal = r.json()
    assert proposal["status"] == "audit_rejected"
    assert proposal["id"] == str(proposal_id)
    assert proposal["decided_at"] is not None

    # A new audit_decision ledger event exists with caused_by linking to the AI event.
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT le.id, le.source_kind, le.source_ref, le.detail
                  FROM ledger_events le
                 WHERE le.tenant_id = :t
                   AND le.engagement_id = :e
                   AND le.source_kind = 'audit_decision'
                """
            ),
            {"t": str(tid), "e": eid},
        ).all()
        assert len(rows) == 1
        audit_event_id, source_kind, source_ref, detail = rows[0]
        assert source_kind == "audit_decision"
        assert str(source_ref) == str(proposal_id)
        assert detail == {"reason": "wrong entity type"}

        cause_rows = conn.execute(
            text("SELECT caused_by_id FROM ledger_event_causes WHERE event_id = :id"),
            {"id": str(audit_event_id)},
        ).all()
        cause_ids = {str(row[0]) for row in cause_rows}
        assert cause_ids == {str(event_id)}


@pytest.mark.asyncio
async def test_audit_decision_cross_tenant_event_id_404(ad_client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a, eid_a = await _new_engagement(ad_client, postgres_engine)
    event_id_a, _ = _seed_event_and_proposal(postgres_engine, tid_a, eid_a, {"node_type": "system", "title": "from A"})
    tid_b, eid_b = await _new_engagement(ad_client, postgres_engine)

    r = await ad_client.post(
        f"/internal/v1/engagements/{eid_b}/audit-decision?tenant_id={tid_b}",
        json={"event_id": str(event_id_a), "reason": None},
    )
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_audit_decision_already_audit_rejected_422(ad_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ad_client, postgres_engine)
    event_id, _ = _seed_event_and_proposal(postgres_engine, tid, eid, {"node_type": "risk", "title": "first"})
    first = await ad_client.post(
        f"/internal/v1/engagements/{eid}/audit-decision?tenant_id={tid}",
        json={"event_id": str(event_id), "reason": "first call"},
    )
    assert first.status_code == 200

    second = await ad_client.post(
        f"/internal/v1/engagements/{eid}/audit-decision?tenant_id={tid}",
        json={"event_id": str(event_id), "reason": "again"},
    )
    assert second.status_code == 422


@pytest.mark.asyncio
async def test_audit_decision_unknown_event_id_404(ad_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(ad_client, postgres_engine)
    r = await ad_client.post(
        f"/internal/v1/engagements/{eid}/audit-decision?tenant_id={tid}",
        json={"event_id": str(uuid.uuid4()), "reason": None},
    )
    assert r.status_code == 404
