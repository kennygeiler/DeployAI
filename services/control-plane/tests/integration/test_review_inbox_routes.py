"""Integration: pilot-refresh E1/E2/E3 — Review Inbox routes + ledger writes.

Covers the full async-HITL lifecycle over `/internal/v1/review-items`:

- E2: file an agent escalation, resolve it with an answer, and prove the
  canonical ``human_escalation_answer`` ledger event landed and is visible
  through the existing ledger API (the knowledge-flywheel write path).
- E3: file a citation dispute and resolve it with a note.
- E1: list filters (kind / status / engagement), open counts for the nav
  badge, dismissal, double-decide rejection, and tenant scoping.
"""

from __future__ import annotations

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

_KEY = "review-inbox-test-key"


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", _KEY)
    clear_engine_cache()
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://test")
    c.headers["X-DeployAI-Internal-Key"] = _KEY
    try:
        yield c
    finally:
        await c.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine, name: str = "review-inbox") -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"), {"t": str(tid), "n": name})
    return tid


async def _new_engagement(client: AsyncClient, tenant_id: uuid.UUID) -> str:
    r = await client.post(f"/internal/v1/engagements?tenant_id={tenant_id}", json={"name": "Inbox Eng"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _file_escalation(
    client: AsyncClient,
    tenant_id: uuid.UUID,
    engagement_id: str,
    **overrides: Any,
) -> dict[str, Any]:
    body = {
        "engagement_id": engagement_id,
        "question": "Who owns the security review for the pilot?",
        "reason": "citation verification failed twice",
        "context_refs": ["11111111-1111-4111-8111-111111111111"],
        "created_by": "agent:kenny",
        **overrides,
    }
    r = await client.post(f"/internal/v1/review-items/escalations?tenant_id={tenant_id}", json=body)
    assert r.status_code == 201, r.text
    return dict(r.json())


async def _ledger_kinds(client: AsyncClient, tenant_id: uuid.UUID, engagement_id: str) -> list[str]:
    r = await client.get(f"/internal/v1/engagements/{engagement_id}/ledger?tenant_id={tenant_id}&limit=100")
    assert r.status_code == 200, r.text
    return [e["source_kind"] for e in r.json()["events"]]


@pytest.mark.asyncio
async def test_escalation_lifecycle_with_answer_reaches_ledger(client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)

    item = await _file_escalation(client, tid, eid)
    assert item["kind"] == "agent_escalation"
    assert item["status"] == "open"
    assert item["payload"]["question"].startswith("Who owns")
    assert item["created_by"] == "agent:kenny"

    # Creation emitted a ledger row.
    assert "review_item_created" in await _ledger_kinds(client, tid, eid)

    # Resolve with an answer → canonical human_escalation_answer event.
    r = await client.post(
        f"/internal/v1/review-items/{item['id']}/resolve?tenant_id={tid}",
        json={
            "resolved_by": "user:kenny",
            "resolution_note": "answered inline",
            "answer_text": "The FDE owns it; review is booked for W23.",
            "answer_citations": ["22222222-2222-4222-8222-222222222222"],
        },
    )
    assert r.status_code == 200, r.text
    resolved = r.json()
    assert resolved["status"] == "resolved"
    assert resolved["resolved_by"] == "user:kenny"
    assert resolved["resolved_at"] is not None
    assert resolved["payload"]["answer_text"].startswith("The FDE owns it")
    assert resolved["payload"]["answer_citations"] == ["22222222-2222-4222-8222-222222222222"]

    kinds = await _ledger_kinds(client, tid, eid)
    assert "human_escalation_answer" in kinds
    assert "review_item_resolved" in kinds

    # The flywheel event carries the answer + citations payload.
    r = await client.get(f"/internal/v1/engagements/{eid}/ledger?tenant_id={tid}&limit=100")
    answer_events = [e for e in r.json()["events"] if e["source_kind"] == "human_escalation_answer"]
    assert len(answer_events) == 1
    detail = answer_events[0]["detail"]
    assert detail["answer_text"] == "The FDE owns it; review is booked for W23."
    assert detail["citations"] == ["22222222-2222-4222-8222-222222222222"]
    assert detail["question"] == "Who owns the security review for the pilot?"

    # Double-resolve is rejected.
    r = await client.post(
        f"/internal/v1/review-items/{item['id']}/resolve?tenant_id={tid}",
        json={"resolved_by": "user:kenny"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_escalation_resolved_without_answer_skips_flywheel_event(
    client: AsyncClient, postgres_engine: Engine
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)
    item = await _file_escalation(client, tid, eid)

    r = await client.post(
        f"/internal/v1/review-items/{item['id']}/resolve?tenant_id={tid}",
        json={"resolved_by": "user:kenny", "resolution_note": "handled out of band"},
    )
    assert r.status_code == 200, r.text
    kinds = await _ledger_kinds(client, tid, eid)
    assert "review_item_resolved" in kinds
    assert "human_escalation_answer" not in kinds


@pytest.mark.asyncio
async def test_citation_dispute_lifecycle(client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)

    r = await client.post(
        f"/internal/v1/review-items/citation-disputes?tenant_id={tid}",
        json={
            "engagement_id": eid,
            "turn_id": "33333333-3333-4333-8333-333333333333",
            "citation_id": "44444444-4444-4444-8444-444444444444",
            "reason": "cited event is about a different stakeholder",
            "created_by": "user:kenny",
        },
    )
    assert r.status_code == 201, r.text
    item = r.json()
    assert item["kind"] == "citation_dispute"
    assert item["payload"]["citation_id"] == "44444444-4444-4444-8444-444444444444"
    assert item["payload"]["turn_id"] == "33333333-3333-4333-8333-333333333333"

    kinds = await _ledger_kinds(client, tid, eid)
    assert "review_item_created" in kinds

    r = await client.post(
        f"/internal/v1/review-items/{item['id']}/resolve?tenant_id={tid}",
        json={"resolved_by": "user:kenny", "resolution_note": "citation corrected in eval set"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "resolved"
    assert r.json()["resolution_note"] == "citation corrected in eval set"
    kinds = await _ledger_kinds(client, tid, eid)
    assert "review_item_resolved" in kinds
    # A dispute resolution is not an escalation answer.
    assert "human_escalation_answer" not in kinds


@pytest.mark.asyncio
async def test_dismiss_emits_ledger_and_blocks_reresolve(client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)
    item = await _file_escalation(client, tid, eid)

    r = await client.post(
        f"/internal/v1/review-items/{item['id']}/dismiss?tenant_id={tid}",
        json={"resolved_by": "user:kenny", "resolution_note": "duplicate of an answered one"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "dismissed"
    assert "review_item_dismissed" in await _ledger_kinds(client, tid, eid)

    r = await client.post(f"/internal/v1/review-items/{item['id']}/resolve?tenant_id={tid}", json={})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_filters_and_counts(client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid_a = await _new_engagement(client, tid)
    eid_b = await _new_engagement(client, tid)

    esc_a = await _file_escalation(client, tid, eid_a)
    await _file_escalation(client, tid, eid_b, question="Second escalation?")
    r = await client.post(
        f"/internal/v1/review-items/citation-disputes?tenant_id={tid}",
        json={"engagement_id": eid_a, "citation_id": "c-1", "reason": "wrong event"},
    )
    assert r.status_code == 201

    # Unfiltered list: newest first, all three.
    r = await client.get(f"/internal/v1/review-items?tenant_id={tid}")
    assert r.status_code == 200
    assert len(r.json()) == 3

    # Kind filter.
    r = await client.get(f"/internal/v1/review-items?tenant_id={tid}&kind=agent_escalation")
    assert {i["kind"] for i in r.json()} == {"agent_escalation"}
    assert len(r.json()) == 2

    # Engagement filter.
    r = await client.get(f"/internal/v1/review-items?tenant_id={tid}&engagement_id={eid_a}")
    assert len(r.json()) == 2

    # Status filter tracks resolution.
    r = await client.post(
        f"/internal/v1/review-items/{esc_a['id']}/resolve?tenant_id={tid}",
        json={"answer_text": "answered", "resolved_by": "u"},
    )
    assert r.status_code == 200
    r = await client.get(f"/internal/v1/review-items?tenant_id={tid}&status=open")
    assert len(r.json()) == 2
    r = await client.get(f"/internal/v1/review-items?tenant_id={tid}&status=resolved")
    assert len(r.json()) == 1

    # Counts endpoint backs the nav badge.
    r = await client.get(f"/internal/v1/review-items/counts?tenant_id={tid}")
    assert r.status_code == 200
    counts = r.json()
    assert counts["open"] == 2
    assert counts["agent_escalation"] == 1
    assert counts["citation_dispute"] == 1
    assert counts["commitment_confirmation"] == 0

    # Invalid enum values are 422, not 500.
    r = await client.get(f"/internal/v1/review-items?tenant_id={tid}&kind=bogus")
    assert r.status_code == 422
    r = await client.get(f"/internal/v1/review-items?tenant_id={tid}&status=bogus")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_tenant_scoping_and_missing_refs(client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine, "inbox-a")
    tid_b = _seed_tenant(postgres_engine, "inbox-b")
    eid_a = await _new_engagement(client, tid_a)
    item = await _file_escalation(client, tid_a, eid_a)

    # Tenant B cannot see or decide tenant A's item.
    r = await client.get(f"/internal/v1/review-items?tenant_id={tid_b}")
    assert r.json() == []
    r = await client.post(f"/internal/v1/review-items/{item['id']}/resolve?tenant_id={tid_b}", json={})
    assert r.status_code == 404

    # Escalations require an engagement in the tenant.
    r = await client.post(
        f"/internal/v1/review-items/escalations?tenant_id={tid_b}",
        json={"engagement_id": eid_a, "question": "q", "reason": "r"},
    )
    assert r.status_code == 404

    # Unknown tenant → 404.
    r = await client.get(f"/internal/v1/review-items?tenant_id={uuid.uuid4()}")
    assert r.status_code == 404
