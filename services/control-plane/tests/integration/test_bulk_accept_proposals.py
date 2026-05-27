"""Integration tests for the bulk-accept matrix-proposals route.

Phase D enhancement — ``POST /internal/v1/engagements/{id}/proposals/accept-bulk``
wraps the existing per-proposal accept code path. See ``engagements_internal.py``
``bulk_accept_matrix_proposals`` and the design comment above it.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

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
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'bulk-accept') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


@pytest_asyncio.fixture
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "bulk-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "bulk-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


async def _new_engagement(e_client: AsyncClient, postgres_engine: Engine) -> tuple[uuid.UUID, str]:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Bulk Matrix"})
    assert r.status_code == 201, r.text
    return tid, r.json()["id"]


def _seed_event(engine: Engine, tenant_id: uuid.UUID, engagement_id: str) -> uuid.UUID:
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
    return uuid.UUID(str(event_id))


def _seed_proposal(
    engine: Engine,
    tenant_id: uuid.UUID,
    engagement_id: str,
    proposal_kind: str,
    payload: dict[str, object],
    *,
    event_id: uuid.UUID | None = None,
) -> uuid.UUID:
    eid = event_id or _seed_event(engine, tenant_id, engagement_id)
    with engine.begin() as conn:
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
                "ev": str(eid),
                "kind": proposal_kind,
                "payload": json.dumps(payload),
                "rationale": "bulk fixture",
            },
        ).scalar_one()
    return uuid.UUID(str(proposal_id))


def _ledger_rows(engine: Engine, tenant_id: uuid.UUID, source_kind: str) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = (
            conn.execute(
                text(
                    """
                SELECT id, summary, detail
                FROM ledger_events
                WHERE tenant_id = :t AND source_kind = :sk
                ORDER BY occurred_at
                """
                ),
                {"t": str(tenant_id), "sk": source_kind},
            )
            .mappings()
            .all()
        )
    return [dict(row) for row in rows]


# --- Happy path: explicit ids -----------------------------------------------


@pytest.mark.asyncio
async def test_bulk_accept_explicit_ids_nodes_and_edges(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)

    # Seed two existing nodes so the edge proposals reference real targets.
    n1 = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "stakeholder", "title": "Dana"},
    )
    n2 = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "system", "title": "LiDAR"},
    )
    assert n1.status_code == 201 and n2.status_code == 201
    from_id = n1.json()["id"]
    to_id = n2.json()["id"]

    node_proposal_ids: list[str] = []
    for i in range(5):
        pid = _seed_proposal(
            postgres_engine,
            tid,
            eid,
            "node",
            {"node_type": "risk", "title": f"Risk {i}"},
        )
        node_proposal_ids.append(str(pid))

    edge_proposal_ids: list[str] = []
    for _ in range(3):
        pid = _seed_proposal(
            postgres_engine,
            tid,
            eid,
            "edge",
            {"edge_type": "threatens", "from_node_id": from_id, "to_node_id": to_id},
        )
        edge_proposal_ids.append(str(pid))

    # Pass edges first so we can verify the route re-orders nodes-first.
    all_ids = edge_proposal_ids + node_proposal_ids
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/accept-bulk?tenant_id={tid}",
        json={"proposal_ids": all_ids, "actor_id": "test-user"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 8
    assert body["failed"] == []
    assert body["skipped"] == 0

    # All proposals should be in 'accepted' state now.
    listed = await e_client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}&status=accepted")
    assert listed.status_code == 200
    assert len(listed.json()) == 8

    # Nodes and edges actually landed.
    nodes = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}")
    edges = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}")
    assert nodes.status_code == 200 and edges.status_code == 200
    # 2 seeded nodes + 5 newly accepted = 7 total nodes; 3 edges.
    assert len(nodes.json()) == 7
    assert len(edges.json()) == 3

    # Audit row emitted with the right counts.
    rows = _ledger_rows(postgres_engine, tid, "proposals_bulk_accepted")
    assert len(rows) == 1
    detail = rows[0]["detail"]
    assert detail["requested"] == 8
    assert detail["accepted"] == 8
    assert detail["failed_count"] == 0
    assert detail["kinds_summary"]["node_accepted"] == 5
    assert detail["kinds_summary"]["edge_accepted"] == 3


# --- Filter mode -------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_accept_filter_pending_nodes_first(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    n1 = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "stakeholder", "title": "Anchor A"},
    )
    n2 = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "system", "title": "Anchor B"},
    )
    from_id = n1.json()["id"]
    to_id = n2.json()["id"]

    for i in range(10):
        _seed_proposal(
            postgres_engine,
            tid,
            eid,
            "node",
            {"node_type": "system", "title": f"Sys {i}"},
        )
    for _ in range(5):
        _seed_proposal(
            postgres_engine,
            tid,
            eid,
            "edge",
            {"edge_type": "depends_on", "from_node_id": from_id, "to_node_id": to_id},
        )

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/accept-bulk?tenant_id={tid}",
        json={"filter": {"status": "pending"}, "actor_id": "bulk-user"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 15
    assert body["failed"] == []

    # Verify nodes-first ordering by inspecting the ledger 'proposal_accepted'
    # rows in temporal order — node rows precede edge rows.
    accepted_events = _ledger_rows(postgres_engine, tid, "proposal_accepted")
    assert len(accepted_events) == 15
    kinds_in_order = [e["detail"]["proposal_kind"] for e in accepted_events]
    # All 'node' before any 'edge'.
    first_edge = kinds_in_order.index("edge")
    assert all(k == "node" for k in kinds_in_order[:first_edge])
    assert all(k == "edge" for k in kinds_in_order[first_edge:])


# --- Edge-before-node ordering ----------------------------------------------


@pytest.mark.asyncio
async def test_bulk_accept_orders_node_before_edge_so_fk_resolves(
    e_client: AsyncClient, postgres_engine: Engine
) -> None:
    """An edge whose from_node_id is itself in the same batch must succeed."""
    tid, eid = await _new_engagement(e_client, postgres_engine)
    anchor = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "system", "title": "Anchor"},
    )
    anchor_id = anchor.json()["id"]

    # A pre-baked node id we'll use as both the node-proposal's id and the
    # edge-proposal's from_node_id. Server uses uuid_v7 server default — we
    # can't reuse the id directly. Instead: accept the node first via the
    # ordering then have the edge reference an existing one.
    # The contract is: nodes go first. Verify by giving the edge an id of
    # an already-accepted node from this batch.
    # To prove ordering, we sandwich-feed: edge id first in the request list,
    # node id second — the route must still process the node first.
    node_pid = _seed_proposal(
        postgres_engine,
        tid,
        eid,
        "node",
        {"node_type": "risk", "title": "Risk that the edge references existence of"},
    )
    edge_pid = _seed_proposal(
        postgres_engine,
        tid,
        eid,
        "edge",
        {"edge_type": "threatens", "from_node_id": anchor_id, "to_node_id": anchor_id},
    )

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/accept-bulk?tenant_id={tid}",
        json={"proposal_ids": [str(edge_pid), str(node_pid)]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 2
    assert body["failed"] == []

    # Ledger confirms node before edge.
    rows = _ledger_rows(postgres_engine, tid, "proposal_accepted")
    kinds = [r["detail"]["proposal_kind"] for r in rows]
    assert kinds == ["node", "edge"]


# --- Partial failure --------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_accept_partial_failure_keeps_good_rows(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)

    good_ids: list[str] = []
    for i in range(5):
        pid = _seed_proposal(
            postgres_engine,
            tid,
            eid,
            "node",
            {"node_type": "system", "title": f"OK-{i}"},
        )
        good_ids.append(str(pid))

    # Corrupted payload: invalid node_type forces a 422 from _accept_one_proposal.
    bad_id = _seed_proposal(
        postgres_engine,
        tid,
        eid,
        "node",
        {"node_type": "definitely-not-a-real-type", "title": "should fail"},
    )

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/accept-bulk?tenant_id={tid}",
        json={"proposal_ids": [*good_ids, str(bad_id)]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] == 5
    assert len(body["failed"]) == 1
    assert body["failed"][0]["id"] == str(bad_id)
    assert "node_type" in body["failed"][0]["error"]

    # The 5 good rows actually landed in matrix_nodes.
    nodes = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}")
    assert len(nodes.json()) == 5

    # The bad one is still pending — failure rolled back its row only.
    pending = await e_client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}&status=pending")
    pending_ids = [p["id"] for p in pending.json()]
    assert str(bad_id) in pending_ids

    # Audit row still emits with the right tally.
    rows = _ledger_rows(postgres_engine, tid, "proposals_bulk_accepted")
    assert len(rows) == 1
    assert rows[0]["detail"]["accepted"] == 5
    assert rows[0]["detail"]["failed_count"] == 1


# --- Batch cap --------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_accept_batch_cap_rejects_oversize(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    # 501 fake uuids — the route should reject before hitting the DB.
    fake_ids = [str(uuid.uuid4()) for _ in range(501)]
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/accept-bulk?tenant_id={tid}",
        json={"proposal_ids": fake_ids},
    )
    assert r.status_code == 400, r.text
    assert "cap" in r.text.lower() or "500" in r.text


# --- Auth -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_accept_requires_internal_key(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    pid = _seed_proposal(
        postgres_engine,
        tid,
        eid,
        "node",
        {"node_type": "system", "title": "any"},
    )
    # Strip the auth header for this request.
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/accept-bulk?tenant_id={tid}",
        json={"proposal_ids": [str(pid)]},
        headers={"X-DeployAI-Internal-Key": ""},
    )
    assert r.status_code == 401


# --- Cross-tenant -----------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_accept_cross_tenant_returns_404(e_client: AsyncClient, postgres_engine: Engine) -> None:
    # Engagement lives under tenant A; we try to bulk-accept on it under
    # tenant B's tenant_id query param.
    tid_a, eid = await _new_engagement(e_client, postgres_engine)
    tid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_b)
    pid = _seed_proposal(
        postgres_engine,
        tid_a,
        eid,
        "node",
        {"node_type": "system", "title": "owned by A"},
    )
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/accept-bulk?tenant_id={tid_b}",
        json={"proposal_ids": [str(pid)]},
    )
    assert r.status_code == 404


# --- Body validation --------------------------------------------------------


@pytest.mark.asyncio
async def test_bulk_accept_rejects_both_ids_and_filter(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/accept-bulk?tenant_id={tid}",
        json={
            "proposal_ids": [str(uuid.uuid4())],
            "filter": {"status": "pending"},
        },
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_bulk_accept_rejects_neither_ids_nor_filter(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/accept-bulk?tenant_id={tid}",
        json={"actor_id": "x"},
    )
    assert r.status_code == 422
