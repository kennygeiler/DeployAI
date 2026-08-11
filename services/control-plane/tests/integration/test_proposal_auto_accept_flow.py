"""Integration: pilot-refresh E4 — confidence-thresholded proposal auto-accept.

Three layers:

1. Settings plumbing — the two policy knobs round-trip through the
   tenant llm-config API and survive a policy-silent PUT.
2. Policy application — ``apply_proposal_auto_accept`` accepts eligible
   proposals with the distinct ``proposal_auto_accepted`` ledger kind,
   flags the deterministic audit sample (``payload.sampling_audit``), and
   queues everything below threshold / without confidence.
3. Route behavior — the extract route with a threshold configured never
   auto-accepts drafts that carry no confidence (the current extractor's
   output shape), so enabling the policy cannot silently bypass review.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from control_plane.agents.llm import get_llm_provider
from control_plane.api.routes.engagements_internal import apply_proposal_auto_accept
from control_plane.db import clear_engine_cache
from control_plane.domain.canonical_memory.matrix import MatrixProposal
from control_plane.main import app
from control_plane.services.proposal_auto_accept import AutoAcceptSettings, sampling_bucket

pytestmark = pytest.mark.integration

_KEY = "auto-accept-test-key"


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


@pytest_asyncio.fixture
async def session_factory(
    postgres_engine: Engine,
    client: AsyncClient,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    # Depends on `client` so DATABASE_URL is already pointed at the container.
    eng = create_async_engine(_async_url(postgres_engine), future=True)
    try:
        yield async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    finally:
        await eng.dispose()


class _FakeLLM:
    id = "fake"

    def __init__(self, response: str = "[]") -> None:
        self.response = response

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = messages, temperature, max_output_tokens
        return self.response

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = temperature, max_output_tokens
        yield self.chat_complete(messages)

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


@pytest.fixture
def fake_llm() -> Iterator[_FakeLLM]:
    fake = _FakeLLM("[]")
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'e4-auto-accept')"), {"t": str(tid)})
    return tid


async def _new_engagement(client: AsyncClient, tenant_id: uuid.UUID) -> str:
    r = await client.post(f"/internal/v1/engagements?tenant_id={tenant_id}", json={"name": "E4"})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _ingest_event(client: AsyncClient, tenant_id: uuid.UUID, engagement_id: str) -> str:
    r = await client.post(
        f"/internal/v1/engagements/{engagement_id}/ingest?tenant_id={tenant_id}",
        json={
            "source": "meeting_note",
            "occurred_at": "2026-08-11T10:00:00+00:00",
            "content": {"text": "Kickoff notes."},
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _seed_proposal(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    tenant_id: uuid.UUID,
    engagement_id: str,
    event_id: str,
    payload: dict[str, Any],
) -> uuid.UUID:
    async with session_factory() as session:
        row = MatrixProposal(
            tenant_id=tenant_id,
            engagement_id=uuid.UUID(engagement_id),
            source_event_id=uuid.UUID(event_id),
            proposal_kind="node",
            payload=payload,
        )
        session.add(row)
        await session.commit()
        return row.id


async def _ledger_kinds(client: AsyncClient, tenant_id: uuid.UUID, engagement_id: str) -> list[str]:
    r = await client.get(f"/internal/v1/engagements/{engagement_id}/ledger?tenant_id={tenant_id}&limit=200")
    assert r.status_code == 200, r.text
    return [e["source_kind"] for e in r.json()["events"]]


# ---------------------------------------------------------------------------
# 1. Settings plumbing
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_llm_config_roundtrips_auto_accept_settings(client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await client.put(
        f"/internal/v1/tenants/{tid}/llm-config",
        json={"provider": "stub", "proposal_auto_accept_threshold": 0.8, "sampling_audit_rate": 0.25},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["proposal_auto_accept_threshold"] == 0.8
    assert body["sampling_audit_rate"] == 0.25

    r = await client.get(f"/internal/v1/tenants/{tid}/llm-config")
    assert r.status_code == 200
    assert r.json()["proposal_auto_accept_threshold"] == 0.8

    # A PUT that does not mention the policy keeps it unchanged.
    r = await client.put(f"/internal/v1/tenants/{tid}/llm-config", json={"provider": "stub"})
    assert r.status_code == 200
    assert r.json()["proposal_auto_accept_threshold"] == 0.8
    assert r.json()["sampling_audit_rate"] == 0.25

    # Explicit null switches the policy off.
    r = await client.put(
        f"/internal/v1/tenants/{tid}/llm-config",
        json={"provider": "stub", "proposal_auto_accept_threshold": None},
    )
    assert r.status_code == 200
    assert r.json()["proposal_auto_accept_threshold"] is None

    # Out-of-range values are rejected.
    r = await client.put(
        f"/internal/v1/tenants/{tid}/llm-config",
        json={"provider": "stub", "proposal_auto_accept_threshold": 1.5},
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# 2. Policy application
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_accepts_flags_and_queues(
    client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)
    event_id = await _ingest_event(client, tid, eid)

    high = await _seed_proposal(
        session_factory,
        tenant_id=tid,
        engagement_id=eid,
        event_id=event_id,
        payload={"node_type": "risk", "title": "High confidence", "confidence": 0.95},
    )
    boundary = await _seed_proposal(
        session_factory,
        tenant_id=tid,
        engagement_id=eid,
        event_id=event_id,
        payload={"node_type": "risk", "title": "Exactly at threshold", "confidence": 0.8},
    )
    low = await _seed_proposal(
        session_factory,
        tenant_id=tid,
        engagement_id=eid,
        event_id=event_id,
        payload={"node_type": "risk", "title": "Low confidence", "confidence": 0.5},
    )
    no_conf = await _seed_proposal(
        session_factory,
        tenant_id=tid,
        engagement_id=eid,
        event_id=event_id,
        payload={"node_type": "risk", "title": "No confidence"},
    )

    settings = AutoAcceptSettings(threshold=0.8, sampling_audit_rate=0.0)
    async with session_factory() as session:
        rows = [await session.get(MatrixProposal, pid) for pid in (high, boundary, low, no_conf)]
        proposals = [r for r in rows if r is not None]
        assert len(proposals) == 4
        accepted = await apply_proposal_auto_accept(
            session,
            tenant_id=tid,
            engagement_id=uuid.UUID(eid),
            proposals=proposals,
            settings=settings,
        )
        await session.commit()

    assert {p.id for p in accepted} == {high, boundary}

    r = await client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}&status=accepted")
    accepted_rows = r.json()
    assert {row["id"] for row in accepted_rows} == {str(high), str(boundary)}
    for row in accepted_rows:
        assert row["decided_by"] == "auto_accept"
        assert row["result_node_id"] is not None

    r = await client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}&status=pending")
    assert {row["id"] for row in r.json()} == {str(low), str(no_conf)}

    kinds = await _ledger_kinds(client, tid, eid)
    assert kinds.count("proposal_auto_accepted") == 2
    assert "proposal_accepted" not in kinds


@pytest.mark.asyncio
async def test_sampling_audit_is_deterministic_and_stays_pending(
    client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)
    event_id = await _ingest_event(client, tid, eid)

    ids = [
        await _seed_proposal(
            session_factory,
            tenant_id=tid,
            engagement_id=eid,
            event_id=event_id,
            payload={"node_type": "risk", "title": f"P{i}", "confidence": 0.9},
        )
        for i in range(12)
    ]

    rate = 0.5
    settings = AutoAcceptSettings(threshold=0.8, sampling_audit_rate=rate)
    expected_audited = {pid for pid in ids if sampling_bucket(pid) < rate}

    async with session_factory() as session:
        rows = [await session.get(MatrixProposal, pid) for pid in ids]
        proposals = [r for r in rows if r is not None]
        accepted = await apply_proposal_auto_accept(
            session,
            tenant_id=tid,
            engagement_id=uuid.UUID(eid),
            proposals=proposals,
            settings=settings,
        )
        await session.commit()

    assert {p.id for p in accepted} == set(ids) - expected_audited

    r = await client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}&status=pending")
    pending = r.json()
    assert {row["id"] for row in pending} == {str(pid) for pid in expected_audited}
    # Audit-sampled proposals are flagged in payload and remain reviewable.
    for row in pending:
        assert row["payload"]["sampling_audit"] is True

    kinds = await _ledger_kinds(client, tid, eid)
    assert kinds.count("proposal_auto_accepted") == len(ids) - len(expected_audited)


# ---------------------------------------------------------------------------
# 3. Route wiring — settings loaded from the tenant row; extract path stays
#    review-everything when the extractor emits no confidence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_policy_loads_settings_from_tenant_llm_config_row(
    client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """`settings=None` (the extract route's call shape) reads the DB knobs."""
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)
    event_id = await _ingest_event(client, tid, eid)
    r = await client.put(
        f"/internal/v1/tenants/{tid}/llm-config",
        json={"provider": "stub", "proposal_auto_accept_threshold": 0.8, "sampling_audit_rate": 0.0},
    )
    assert r.status_code == 200

    high = await _seed_proposal(
        session_factory,
        tenant_id=tid,
        engagement_id=eid,
        event_id=event_id,
        payload={"node_type": "risk", "title": "Scored", "confidence": 0.9},
    )
    unscored = await _seed_proposal(
        session_factory,
        tenant_id=tid,
        engagement_id=eid,
        event_id=event_id,
        payload={"node_type": "risk", "title": "Unscored"},
    )

    async with session_factory() as session:
        rows = [await session.get(MatrixProposal, pid) for pid in (high, unscored)]
        proposals = [r for r in rows if r is not None]
        accepted = await apply_proposal_auto_accept(
            session,
            tenant_id=tid,
            engagement_id=uuid.UUID(eid),
            proposals=proposals,
        )
        await session.commit()

    assert [p.id for p in accepted] == [high]
    r = await client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}&status=pending")
    assert {row["id"] for row in r.json()} == {str(unscored)}


@pytest.mark.asyncio
async def test_policy_is_off_without_a_settings_row(
    client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)
    event_id = await _ingest_event(client, tid, eid)
    pid = await _seed_proposal(
        session_factory,
        tenant_id=tid,
        engagement_id=eid,
        event_id=event_id,
        payload={"node_type": "risk", "title": "Scored", "confidence": 0.99},
    )
    async with session_factory() as session:
        row = await session.get(MatrixProposal, pid)
        assert row is not None
        accepted = await apply_proposal_auto_accept(
            session,
            tenant_id=tid,
            engagement_id=uuid.UUID(eid),
            proposals=[row],
        )
        await session.commit()
    assert accepted == []
    r = await client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}&status=pending")
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_extract_route_without_confidence_never_auto_accepts(
    client: AsyncClient,
    postgres_engine: Engine,
    fake_llm: _FakeLLM,
) -> None:
    """No tenant llm-config row (policy off) — the env-fallback FakeLLM drives
    extraction and every draft queues for review, matching today's extractor
    output which carries no confidence field."""
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)
    event_id = await _ingest_event(client, tid, eid)

    fake_llm.response = json.dumps([{"kind": "node", "node_type": "risk", "title": "Unscored draft", "rationale": "r"}])
    r = await client.post(f"/internal/v1/engagements/{eid}/extract?tenant_id={tid}&event_id={event_id}")
    assert r.status_code == 201, r.text
    created = r.json()
    assert len(created) == 1
    assert created[0]["status"] == "pending"
    assert "proposal_auto_accepted" not in await _ledger_kinds(client, tid, eid)
