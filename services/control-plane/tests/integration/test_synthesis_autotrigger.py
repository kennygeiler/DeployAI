"""Integration — v2 Phase 0.5 follow-up: production auto-enqueue path.

Confirms that accepting a matrix proposal via the real internal API route
populates ``detail.node_type``, that the emitter dispatcher reads the hint,
that the resulting ``synthesis_refresh_jobs`` row is drained successfully,
and that a ``kenny`` ``matrix_insights`` row lands in the database — the
end-to-end auto-enqueue loop that was inert before this PR.
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

from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache
from control_plane.main import app
from control_plane.scenarios.bluestate import (
    ENGAGEMENT_ID as BLUESTATE_ENGAGEMENT_ID,
)
from control_plane.workers import synthesizer as synth_mod

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


class _ScriptedLLM:
    """Deterministic JSON-replying provider for the synthesizer."""

    id = "scripted"

    def __init__(self) -> None:
        self.calls = 0

    def _build_reply(self, messages: list[ChatMessage]) -> str:
        from control_plane.agents.synthesis.claim_cite import CITATION_RE

        blob = " ".join(str(m.get("content", "")) for m in messages)  # type: ignore[arg-type]
        seen: set[str] = set()
        ids: list[str] = []
        for kind, raw in CITATION_RE.findall(blob):
            if kind != "event":
                continue
            if raw in seen:
                continue
            seen.add(raw)
            ids.append(raw)
        assert ids, "synthesizer prompt must surface at least one [event:UUID]"
        e1 = ids[0]
        e2 = ids[1] if len(ids) > 1 else e1
        body = (
            f"The decision was accepted via the proposals API [event:{e1}].\n\n"
            f"Upstream evidence supports the rationale [event:{e2}]."
        )
        return json.dumps(
            {
                "title": "Decision provenance: API-accepted node",
                "body": body,
                "claim_citations": [
                    {"paragraph": 0, "event_ids": [e1]},
                    {"paragraph": 1, "event_ids": [e2]},
                ],
            }
        )

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = temperature, max_output_tokens
        self.calls += 1
        return self._build_reply(messages)

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


@pytest_asyncio.fixture
async def s_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "auto-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=60.0)
    client.headers["X-DeployAI-Internal-Key"] = "auto-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.fixture
def scripted_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[_ScriptedLLM]:
    fake = _ScriptedLLM()
    monkeypatch.setattr(synth_mod, "get_llm_provider", lambda: fake)

    async def _resolve_to_fake(_session: Any, _tenant_id: uuid.UUID, _env_fallback: Any) -> _ScriptedLLM:
        return fake

    monkeypatch.setattr(synth_mod, "resolve_tenant_llm_provider", _resolve_to_fake)
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


def _seed_event_and_pending_proposal(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_type: str,
    title: str,
) -> uuid.UUID:
    """Insert a canonical event + a pending matrix_proposals row of node-kind.

    Mirrors the shape produced by the matrix extractor; the proposal awaits
    user acceptance via the production route.
    """
    with engine.begin() as conn:
        event_id = conn.execute(
            text(
                "INSERT INTO canonical_memory_events (tenant_id, engagement_id, event_type, occurred_at) "
                "VALUES (:t, :e, 'ingest.meeting_note', now()) RETURNING id"
            ),
            {"t": str(tenant_id), "e": str(engagement_id)},
        ).scalar_one()
        proposal_id = conn.execute(
            text(
                "INSERT INTO matrix_proposals "
                "(tenant_id, engagement_id, source_event_id, proposal_kind, payload, rationale) "
                "VALUES (:t, :e, :ev, 'node', CAST(:payload AS jsonb), :rat) RETURNING id"
            ),
            {
                "t": str(tenant_id),
                "e": str(engagement_id),
                "ev": str(event_id),
                "payload": json.dumps({"node_type": node_type, "title": title}),
                "rat": "fixture",
            },
        ).scalar_one()
    return proposal_id


@pytest.mark.asyncio
async def test_accept_decision_proposal_via_route_drives_synthesis(
    s_client: AsyncClient,
    postgres_engine: Engine,
    scripted_llm: _ScriptedLLM,
) -> None:
    """Seed BlueState; submit a fresh pending decision proposal; accept via the
    public route; drain synthesis jobs; assert a ``kenny`` synthesis row lands.
    """
    tid = uuid.uuid4()
    bluestate = await s_client.post(
        f"/internal/v1/admin/seed-scenarios/bluestate?tenant_id={tid}",
        json={"force": False},
    )
    assert bluestate.status_code == 200, bluestate.text
    eid = uuid.UUID(bluestate.json()["engagement_id"])
    assert eid == uuid.UUID(BLUESTATE_ENGAGEMENT_ID)

    proposal_id = _seed_event_and_pending_proposal(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="decision",
        title="Auto-enqueue smoke decision",
    )

    accept = await s_client.post(
        f"/internal/v1/engagements/{eid}/proposals/{proposal_id}/accept?tenant_id={tid}",
        json={"actor_id": "auto-test-user"},
    )
    assert accept.status_code == 200, accept.text
    proposal = accept.json()
    assert proposal["status"] == "accepted"
    assert proposal["result_node_id"] is not None

    with postgres_engine.connect() as c:
        accept_event = (
            c.execute(
                text(
                    "SELECT detail FROM ledger_events "
                    "WHERE tenant_id = :t AND engagement_id = :e "
                    "AND source_kind = 'proposal_accepted' AND source_ref = :p"
                ),
                {"t": str(tid), "e": str(eid), "p": proposal_id},
            )
            .mappings()
            .first()
        )
        assert accept_event is not None
        assert accept_event["detail"].get("node_type") == "decision"

        pending = c.execute(
            text(
                "SELECT count(*) FROM synthesis_refresh_jobs "
                "WHERE tenant_id = :t AND engagement_id = :e AND kind = 'decision_provenance' "
                "AND status = 'pending'"
            ),
            {"t": str(tid), "e": str(eid)},
        ).scalar_one()
        assert pending >= 1, "emitter dispatcher must have enqueued a refresh job"

    drain = await s_client.post(f"/internal/v1/admin/synthesis/drain?tenant_id={tid}&engagement_id={eid}")
    assert drain.status_code == 200, drain.text
    drain_result = drain.json()
    assert drain_result["succeeded"] >= 1
    assert scripted_llm.calls >= 1

    with postgres_engine.connect() as c:
        row = (
            c.execute(
                text(
                    "SELECT agent, insight_type, dedup_key FROM matrix_insights "
                    "WHERE tenant_id = :t AND engagement_id = :e "
                    "AND agent = 'kenny' AND insight_type = 'decision_provenance_summary' "
                    "AND dedup_key = :k"
                ),
                {
                    "t": str(tid),
                    "e": str(eid),
                    "k": f"kenny:decision_provenance:{proposal['result_node_id']}",
                },
            )
            .mappings()
            .first()
        )
        assert row is not None, "expected a kenny decision_provenance_summary row for the accepted decision"
