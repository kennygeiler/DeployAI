"""Engagements internal API (integration) — Phase 1."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'engagements') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_user(engine: Engine, user_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_users (id, tenant_id, user_name) VALUES (:u, :t, 'member')"),
            {"u": str(user_id), "t": str(tenant_id)},
        )


@pytest_asyncio.fixture
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "e-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "e-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_create_list_get_engagement(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "NYC DOT LiDAR", "customer_account": "NYC DOT"},
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["name"] == "NYC DOT LiDAR"
    assert created["customer_account"] == "NYC DOT"
    assert created["current_phase"] == "P1_pre_engagement"
    assert created["status"] == "active"
    eid = created["id"]

    r2 = await e_client.get(f"/internal/v1/engagements?tenant_id={tid}")
    assert r2.status_code == 200
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0]["id"] == eid

    r3 = await e_client.get(f"/internal/v1/engagements/{eid}?tenant_id={tid}")
    assert r3.status_code == 200
    assert r3.json()["id"] == eid


@pytest.mark.asyncio
async def test_engagement_unknown_tenant_404(e_client: AsyncClient) -> None:
    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={uuid.uuid4()}",
        json={"name": "ghost"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_engagement_invalid_phase_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "bad phase", "current_phase": "P9_nope"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_engagement_tenant_isolation(e_client: AsyncClient, postgres_engine: Engine) -> None:
    """An engagement created under tenant A is not visible to tenant B."""
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a)
    _ins_tenant(postgres_engine, tid_b)

    r = await e_client.post(
        f"/internal/v1/engagements?tenant_id={tid_a}",
        json={"name": "tenant A only"},
    )
    assert r.status_code == 201
    eid = r.json()["id"]

    r_list = await e_client.get(f"/internal/v1/engagements?tenant_id={tid_b}")
    assert r_list.status_code == 200
    assert r_list.json() == []

    r_get = await e_client.get(f"/internal/v1/engagements/{eid}?tenant_id={tid_b}")
    assert r_get.status_code == 404


@pytest.mark.asyncio
async def test_engagement_member_crud(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    _ins_user(postgres_engine, uid, tid)

    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "NYC DOT"})
    assert r.status_code == 201
    eid = r.json()["id"]

    rm = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "fde"},
    )
    assert rm.status_code == 201, rm.text
    member = rm.json()
    assert member["role"] == "fde"
    assert member["user_id"] == str(uid)
    mid = member["id"]

    rl = await e_client.get(f"/internal/v1/engagements/{eid}/members?tenant_id={tid}")
    assert rl.status_code == 200
    assert len(rl.json()) == 1

    rdup = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "biz_dev"},
    )
    assert rdup.status_code == 409

    rdel = await e_client.delete(f"/internal/v1/engagements/{eid}/members/{mid}?tenant_id={tid}")
    assert rdel.status_code == 204

    rl2 = await e_client.get(f"/internal/v1/engagements/{eid}/members?tenant_id={tid}")
    assert rl2.json() == []


@pytest.mark.asyncio
async def test_engagement_member_invalid_role_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    _ins_user(postgres_engine, uid, tid)
    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "x"})
    eid = r.json()["id"]
    rm = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "platform_admin"},
    )
    assert rm.status_code == 422


async def _new_engagement(e_client: AsyncClient, postgres_engine: Engine) -> tuple[uuid.UUID, str]:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Matrix"})
    return tid, r.json()["id"]


@pytest.mark.asyncio
async def test_matrix_node_crud(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)

    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "system", "title": "LiDAR ingest"},
    )
    assert created.status_code == 201, created.text
    node = created.json()
    assert node["node_type"] == "system"
    assert node["attributes"] == {}
    assert node["evidence_event_ids"] == []
    node_id = node["id"]

    got = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}")
    assert got.status_code == 200
    assert got.json()["title"] == "LiDAR ingest"

    listed = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    patched = await e_client.patch(
        f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}",
        json={"title": "LiDAR ingest pipeline", "status": "at_risk", "attributes": {"owner": "DOT"}},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["title"] == "LiDAR ingest pipeline"
    assert patched.json()["status"] == "at_risk"
    assert patched.json()["attributes"] == {"owner": "DOT"}

    deleted = await e_client.delete(f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}")
    assert deleted.status_code == 204
    missing = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes/{node_id}?tenant_id={tid}")
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_matrix_node_invalid_type_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "gremlin", "title": "not a valid type"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_matrix_edge_crud(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)

    async def _node(node_type: str, title: str) -> str:
        r = await e_client.post(
            f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
            json={"node_type": node_type, "title": title},
        )
        return str(r.json()["id"])

    risk_id = await _node("risk", "Calibration slip")
    system_id = await _node("system", "LiDAR ingest")

    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}",
        json={"edge_type": "threatens", "from_node_id": risk_id, "to_node_id": system_id},
    )
    assert created.status_code == 201, created.text
    assert created.json()["edge_type"] == "threatens"

    listed = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}")
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    deleted = await e_client.delete(
        f"/internal/v1/engagements/{eid}/matrix/edges/{created.json()['id']}?tenant_id={tid}"
    )
    assert deleted.status_code == 204


@pytest.mark.asyncio
async def test_matrix_edge_unknown_node_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    created = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}",
        json={"node_type": "system", "title": "only node"},
    )
    node_id = created.json()["id"]
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/matrix/edges?tenant_id={tid}",
        json={"edge_type": "depends_on", "from_node_id": node_id, "to_node_id": str(uuid.uuid4())},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_ingest_interaction_creates_canonical_event(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/ingest?tenant_id={tid}",
        json={
            "source": "manual_import",
            "occurred_at": "2026-05-09T15:00:00+00:00",
            "content": {"text": "Calibration walkthrough — risk: drift on north corridor."},
            "source_ref": "https://example/notes/42",
        },
    )
    assert r.status_code == 201, r.text
    event = r.json()
    assert event["event_type"] == "ingest.manual_import"
    assert event["engagement_id"] == eid
    assert event["source_ref"] == "https://example/notes/42"
    assert event["payload"]["content"]["text"].startswith("Calibration walkthrough")


@pytest.mark.asyncio
async def test_ingest_dedup_key_is_idempotent(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    body = {
        "source": "meeting_note",
        "occurred_at": "2026-05-09T15:00:00+00:00",
        "content": {"text": "first"},
        "dedup_key": "otter:meeting:abc123:v1",
    }
    first = await e_client.post(f"/internal/v1/engagements/{eid}/ingest?tenant_id={tid}", json=body)
    assert first.status_code == 201
    # Re-post with the same dedup_key (content varied to prove the first wins).
    body["content"] = {"text": "second — should be ignored"}
    second = await e_client.post(f"/internal/v1/engagements/{eid}/ingest?tenant_id={tid}", json=body)
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["payload"]["content"]["text"] == "first"


@pytest.mark.asyncio
async def test_ingest_unknown_source_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/ingest?tenant_id={tid}",
        json={
            "source": "smoke_signal",
            "occurred_at": "2026-05-09T15:00:00+00:00",
            "content": {"text": "nope"},
        },
    )
    assert r.status_code == 422


def _seed_event_and_proposal(
    engine: Engine,
    tenant_id: uuid.UUID,
    engagement_id: str,
    proposal_kind: str,
    payload: dict[str, object],
) -> uuid.UUID:
    """Insert a canonical event + a pending matrix_proposals row; return the proposal id."""
    import json

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
    return proposal_id


@pytest.mark.asyncio
async def test_matrix_proposal_accept_creates_node(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    proposal_id = _seed_event_and_proposal(
        postgres_engine,
        tid,
        eid,
        "node",
        {"node_type": "system", "title": "LiDAR ingest"},
    )

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/{proposal_id}/accept?tenant_id={tid}",
        json={"actor_id": "test-user"},
    )
    assert r.status_code == 200, r.text
    proposal = r.json()
    assert proposal["status"] == "accepted"
    assert proposal["decided_by"] == "test-user"
    assert proposal["result_node_id"] is not None

    listed = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}")
    assert listed.status_code == 200
    nodes = listed.json()
    assert len(nodes) == 1
    assert nodes[0]["title"] == "LiDAR ingest"
    # Evidence: the canonical event that produced this proposal is cited.
    assert nodes[0]["evidence_event_ids"] == [proposal["source_event_id"]]


@pytest.mark.asyncio
async def test_matrix_proposal_reject_does_not_create_node(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    proposal_id = _seed_event_and_proposal(
        postgres_engine,
        tid,
        eid,
        "node",
        {"node_type": "risk", "title": "Calibration drift"},
    )

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/{proposal_id}/reject?tenant_id={tid}",
        json={"actor_id": "test-user"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "rejected"

    listed = await e_client.get(f"/internal/v1/engagements/{eid}/matrix/nodes?tenant_id={tid}")
    assert listed.json() == []


@pytest.mark.asyncio
async def test_matrix_proposal_double_decision_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    proposal_id = _seed_event_and_proposal(
        postgres_engine,
        tid,
        eid,
        "node",
        {"node_type": "decision", "title": "Phased rollout"},
    )

    first = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/{proposal_id}/accept?tenant_id={tid}",
        json={},
    )
    assert first.status_code == 200
    second = await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/{proposal_id}/reject?tenant_id={tid}",
        json={},
    )
    assert second.status_code == 422


@pytest.mark.asyncio
async def test_matrix_proposal_list_filters_by_status(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    pid = _seed_event_and_proposal(postgres_engine, tid, eid, "node", {"node_type": "system", "title": "Pending one"})
    _seed_event_and_proposal(postgres_engine, tid, eid, "node", {"node_type": "system", "title": "Pending two"})

    listed = await e_client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}")
    assert listed.status_code == 200
    assert len(listed.json()) == 2

    await e_client.post(
        f"/internal/v1/engagements/{eid}/proposals/{pid}/accept?tenant_id={tid}",
        json={},
    )
    pending = await e_client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}&status=pending")
    assert len(pending.json()) == 1
    accepted = await e_client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}&status=accepted")
    assert len(accepted.json()) == 1


# --- Phase 6.2c — /extract integration -------------------------------------


class _FakeLLM:
    """Stub LLM that returns a fixed string; counts call invocations."""

    id = "fake"

    def __init__(self, response: str = "[]") -> None:
        self.response = response
        self.calls = 0

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = messages, temperature, max_output_tokens
        self.calls += 1
        return self.response

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = messages, temperature, max_output_tokens
        for chunk in (self.chat_complete(messages),):
            yield chunk

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


async def _ingest(e_client: AsyncClient, tid: uuid.UUID, eid: str, text_content: str) -> str:
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/ingest?tenant_id={tid}",
        json={
            "source": "meeting_note",
            "occurred_at": "2026-05-09T15:00:00+00:00",
            "content": {"text": text_content},
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


@pytest.mark.asyncio
async def test_extract_creates_proposals_from_event(
    e_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    import json as _json

    tid, eid = await _new_engagement(e_client, postgres_engine)
    event_id = await _ingest(e_client, tid, eid, "Decided phased rollout for week 3.")

    fake_llm.response = _json.dumps(
        [
            {
                "kind": "node",
                "node_type": "decision",
                "title": "Phased rollout",
                "rationale": "Team agreed on phasing.",
            }
        ]
    )
    r = await e_client.post(f"/internal/v1/engagements/{eid}/extract?tenant_id={tid}&event_id={event_id}")
    assert r.status_code == 201, r.text
    proposals = r.json()
    assert len(proposals) == 1
    p = proposals[0]
    assert p["proposal_kind"] == "node"
    assert p["status"] == "pending"
    assert p["source_event_id"] == event_id
    assert p["payload"]["title"] == "Phased rollout"


@pytest.mark.asyncio
async def test_extract_is_idempotent_without_force(
    e_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    import json as _json

    tid, eid = await _new_engagement(e_client, postgres_engine)
    event_id = await _ingest(e_client, tid, eid, "Calibration risk on north corridor.")

    fake_llm.response = _json.dumps([{"kind": "node", "node_type": "risk", "title": "Calibration drift"}])
    first = await e_client.post(f"/internal/v1/engagements/{eid}/extract?tenant_id={tid}&event_id={event_id}")
    assert first.status_code == 201
    first_ids = [p["id"] for p in first.json()]
    calls_after_first = fake_llm.calls

    # Re-run without force: LLM should NOT be called; existing proposals returned.
    second = await e_client.post(f"/internal/v1/engagements/{eid}/extract?tenant_id={tid}&event_id={event_id}")
    assert second.status_code == 201
    second_ids = [p["id"] for p in second.json()]
    assert sorted(second_ids) == sorted(first_ids)
    assert fake_llm.calls == calls_after_first


@pytest.mark.asyncio
async def test_extract_force_drops_pending_and_reruns(
    e_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    import json as _json

    tid, eid = await _new_engagement(e_client, postgres_engine)
    event_id = await _ingest(e_client, tid, eid, "Initial note.")

    fake_llm.response = _json.dumps([{"kind": "node", "node_type": "risk", "title": "Old draft"}])
    first = await e_client.post(f"/internal/v1/engagements/{eid}/extract?tenant_id={tid}&event_id={event_id}")
    first_ids = {p["id"] for p in first.json()}

    fake_llm.response = _json.dumps([{"kind": "node", "node_type": "decision", "title": "Fresh draft"}])
    forced = await e_client.post(
        f"/internal/v1/engagements/{eid}/extract?tenant_id={tid}&event_id={event_id}&force=true"
    )
    assert forced.status_code == 201
    forced_ids = {p["id"] for p in forced.json()}
    # Old pending proposal id is gone, new pending id is fresh.
    assert forced_ids.isdisjoint(first_ids)
    titles = [p["payload"]["title"] for p in forced.json()]
    assert titles == ["Fresh draft"]


@pytest.mark.asyncio
async def test_extract_unknown_event_404(e_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(f"/internal/v1/engagements/{eid}/extract?tenant_id={tid}&event_id={uuid.uuid4()}")
    assert r.status_code == 404
