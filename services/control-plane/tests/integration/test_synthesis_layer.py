"""Integration: v2 Phase 0.5 compounding-synthesis layer.

Covers the three core paths called out in the scope-v2 §3 brief:
  - Happy path: ``proposal_accepted`` enqueues a ``decision_provenance`` job,
    drain produces a ``matrix_insights`` row with ``agent='kenny'``,
    non-empty ``source_event_ids``, and a body that passes claim-cite
    validation.
  - Stale: deleting a source ledger event flips ``stale=true`` and emits a
    ``synthesis_stale_flagged`` ledger event via ``mark_stale_for_deleted_sources``.
  - Budget exhausted: ``check_and_charge`` monkeypatched to deny → a
    ``synthesis_failed`` ledger event is emitted and no synthesis row appears.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.llm import get_llm_provider
from control_plane.agents.synthesis.claim_cite import validate_per_claim_cites
from control_plane.db import clear_engine_cache, get_app_db_session
from control_plane.ledger import emit_ledger_event
from control_plane.main import app
from control_plane.workers import synthesizer as synth_mod
from control_plane.workers.synthesizer import mark_stale_for_deleted_sources

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'synth-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_engagement(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'synth-eng', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tenant_id)},
        )
    return eid


def _ins_matrix_node(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_type: str,
    title: str,
) -> uuid.UUID:
    nid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_nodes "
                "(id, tenant_id, engagement_id, node_type, title, attributes, evidence_event_ids) "
                "VALUES (:i, :t, :e, :nt, :ti, '{}'::jsonb, '{}'::uuid[])"
            ),
            {"i": str(nid), "t": str(tenant_id), "e": str(engagement_id), "nt": node_type, "ti": title},
        )
    return nid


class _ScriptedLLM:
    """Deterministic JSON-replying provider for the synthesizer."""

    id = "scripted"

    def __init__(self, builder: Any) -> None:
        self._builder = builder
        self.calls = 0

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = temperature, max_output_tokens
        self.calls += 1
        return self._builder(messages)

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


def _extract_event_ids_from_prompt(messages: list[ChatMessage]) -> list[uuid.UUID]:
    """Pull every [event:UUID] reference the synthesizer included in its prompt."""
    from control_plane.agents.synthesis.claim_cite import CITATION_RE

    text_blob = " ".join(str(m.get("content", "")) for m in messages)  # type: ignore[arg-type]
    found: list[uuid.UUID] = []
    for kind, raw in CITATION_RE.findall(text_blob):
        if kind == "event":
            try:
                found.append(uuid.UUID(raw))
            except ValueError:
                continue
    seen: set[uuid.UUID] = set()
    unique: list[uuid.UUID] = []
    for fid in found:
        if fid in seen:
            continue
        seen.add(fid)
        unique.append(fid)
    return unique


def _build_valid_reply(messages: list[ChatMessage]) -> str:
    ids = _extract_event_ids_from_prompt(messages)
    assert ids, "test fixture must surface at least one [event:UUID] in the prompt"
    e1 = str(ids[0])
    e2 = str(ids[1]) if len(ids) > 1 else e1
    body = (
        f"The decision was approved after the proposal landed [event:{e1}].\n\n"
        f"Upstream evidence supports the rationale [event:{e2}]."
    )
    return json.dumps(
        {
            "title": "Decision provenance: AD migration",
            "body": body,
            "claim_citations": [
                {"paragraph": 0, "event_ids": [e1]},
                {"paragraph": 1, "event_ids": [e2]},
            ],
        }
    )


@pytest_asyncio.fixture
async def s_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "synth-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=60.0)
    client.headers["X-DeployAI-Internal-Key"] = "synth-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.fixture
def scripted_llm(monkeypatch: pytest.MonkeyPatch) -> Iterator[_ScriptedLLM]:
    fake = _ScriptedLLM(_build_valid_reply)
    # The synthesizer imports `get_llm_provider` directly and is NOT routed
    # through FastAPI Depends, so dependency_overrides alone wouldn't reach it.
    # Patch the module-local reference + the FastAPI dep so both call sites
    # land on the same scripted provider.
    monkeypatch.setattr(synth_mod, "get_llm_provider", lambda: fake)

    async def _resolve_to_fake(_session: Any, _tenant_id: uuid.UUID, _env_fallback: Any) -> _ScriptedLLM:
        return fake

    monkeypatch.setattr(synth_mod, "resolve_tenant_llm_provider", _resolve_to_fake)
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def _seed_decision_with_ledger(
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    decision_node_id: uuid.UUID,
    postgres_engine: Engine,
) -> uuid.UUID:
    """Emit a proposal_accepted ledger event tied to ``decision_node_id`` and
    return its event id. Also enqueues a synthesis job via the emitter hook.
    """
    async for session in get_app_db_session():
        now = datetime.now(UTC)
        upstream = await emit_ledger_event(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            occurred_at=now,
            actor_kind="user",
            actor_id="seed",
            source_kind="manual_capture",
            source_ref=None,
            summary="Upstream rationale event",
            detail={},
        )
        accepted = await emit_ledger_event(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            occurred_at=now,
            actor_kind="user",
            actor_id="seed",
            source_kind="proposal_accepted",
            source_ref=None,
            summary="proposal accepted: AD migration",
            detail={"node_type": "decision"},
            caused_by=[upstream.id],
            affects=[("matrix_node", decision_node_id)],
        )
        await session.commit()
        return accepted.id


@pytest.mark.asyncio
async def test_drain_produces_kenny_decision_provenance_row(
    s_client: AsyncClient, postgres_engine: Engine, scripted_llm: _ScriptedLLM
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    decision_id = _ins_matrix_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="decision",
        title="Active Directory migration",
    )
    await _seed_decision_with_ledger(
        tenant_id=tid,
        engagement_id=eid,
        decision_node_id=decision_id,
        postgres_engine=postgres_engine,
    )

    # Synthesis job must be auto-enqueued by the emitter hook.
    with postgres_engine.connect() as c:
        pending = c.execute(
            text(
                "SELECT count(*) FROM synthesis_refresh_jobs "
                "WHERE tenant_id = :t AND engagement_id = :e AND status = 'pending'"
            ),
            {"t": str(tid), "e": str(eid)},
        ).scalar_one()
        assert pending >= 1

    drain = await s_client.post(f"/internal/v1/admin/synthesis/drain?tenant_id={tid}&engagement_id={eid}")
    assert drain.status_code == 200, drain.text
    result = drain.json()
    assert result["succeeded"] >= 1
    assert result["failed"] == 0
    assert scripted_llm.calls >= 1

    with postgres_engine.connect() as c:
        row = (
            c.execute(
                text(
                    "SELECT id, agent, insight_type, body, citation_event_ids, last_refreshed_at, stale "
                    "FROM matrix_insights WHERE tenant_id = :t AND engagement_id = :e AND agent = 'kenny'"
                ),
                {"t": str(tid), "e": str(eid)},
            )
            .mappings()
            .first()
        )
        assert row is not None, "expected a kenny synthesis row after drain"
        assert row["insight_type"] == "decision_provenance_summary"
        assert row["stale"] is False
        assert row["last_refreshed_at"] is not None
        assert len(row["citation_event_ids"]) >= 1
        report = validate_per_claim_cites(row["body"])
        assert report.ok, f"body failed claim-cite validation: {report.missing_cite_paragraphs}"

        # Audit ledger event must be emitted.
        audit = c.execute(
            text(
                "SELECT count(*) FROM ledger_events "
                "WHERE tenant_id = :t AND engagement_id = :e AND source_kind = 'agent_synthesis_emitted'"
            ),
            {"t": str(tid), "e": str(eid)},
        ).scalar_one()
        assert audit >= 1


@pytest.mark.asyncio
async def test_stale_helper_flags_when_source_event_deleted(
    s_client: AsyncClient, postgres_engine: Engine, scripted_llm: _ScriptedLLM
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    decision_id = _ins_matrix_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="decision",
        title="Stale-path decision",
    )
    await _seed_decision_with_ledger(
        tenant_id=tid,
        engagement_id=eid,
        decision_node_id=decision_id,
        postgres_engine=postgres_engine,
    )
    drain = await s_client.post(f"/internal/v1/admin/synthesis/drain?tenant_id={tid}&engagement_id={eid}")
    assert drain.status_code == 200, drain.text

    with postgres_engine.connect() as c:
        row = (
            c.execute(
                text(
                    "SELECT id, citation_event_ids FROM matrix_insights "
                    "WHERE tenant_id = :t AND engagement_id = :e AND agent = 'kenny'"
                ),
                {"t": str(tid), "e": str(eid)},
            )
            .mappings()
            .first()
        )
        assert row is not None
        cited_events = row["citation_event_ids"]
        assert len(cited_events) >= 1

    # Delete one of the source events. ON DELETE CASCADE for ledger_event_affects /
    # ledger_event_causes will follow.
    with postgres_engine.begin() as c:
        c.execute(text("DELETE FROM ledger_events WHERE id = :e"), {"e": str(cited_events[0])})

    async for session in get_app_db_session():
        flagged = await mark_stale_for_deleted_sources(
            session,
            tenant_id=tid,
            engagement_id=eid,
            now=datetime.now(UTC),
        )
        await session.commit()
        assert flagged, "expected at least one row flagged stale"
        break

    with postgres_engine.connect() as c:
        stale_row = (
            c.execute(
                text(
                    "SELECT stale FROM matrix_insights WHERE tenant_id = :t AND engagement_id = :e AND agent = 'kenny'"
                ),
                {"t": str(tid), "e": str(eid)},
            )
            .mappings()
            .first()
        )
        assert stale_row is not None
        assert stale_row["stale"] is True

        stale_event = c.execute(
            text(
                "SELECT count(*) FROM ledger_events "
                "WHERE tenant_id = :t AND engagement_id = :e AND source_kind = 'synthesis_stale_flagged'"
            ),
            {"t": str(tid), "e": str(eid)},
        ).scalar_one()
        assert stale_event >= 1


@pytest.mark.asyncio
async def test_budget_exhausted_emits_failure_and_writes_no_insight(
    s_client: AsyncClient,
    postgres_engine: Engine,
    scripted_llm: _ScriptedLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    decision_id = _ins_matrix_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="decision",
        title="Budget-blocked decision",
    )
    await _seed_decision_with_ledger(
        tenant_id=tid,
        engagement_id=eid,
        decision_node_id=decision_id,
        postgres_engine=postgres_engine,
    )

    async def _deny(*args: Any, **kwargs: Any) -> bool:
        return False

    monkeypatch.setattr(synth_mod, "check_and_charge", _deny)

    drain = await s_client.post(f"/internal/v1/admin/synthesis/drain?tenant_id={tid}&engagement_id={eid}")
    assert drain.status_code == 200, drain.text
    result = drain.json()
    assert result["succeeded"] == 0
    # Job ends in "failed" status because the worker returns None for
    # budget-exhausted paths.
    assert result["failed"] + result["skipped"] >= 1
    assert scripted_llm.calls == 0

    with postgres_engine.connect() as c:
        rows = c.execute(
            text(
                "SELECT count(*) FROM matrix_insights WHERE tenant_id = :t AND engagement_id = :e AND agent = 'kenny'"
            ),
            {"t": str(tid), "e": str(eid)},
        ).scalar_one()
        assert rows == 0

        failed_event = c.execute(
            text(
                "SELECT count(*) FROM ledger_events "
                "WHERE tenant_id = :t AND engagement_id = :e AND source_kind = 'synthesis_failed'"
            ),
            {"t": str(tid), "e": str(eid)},
        ).scalar_one()
        assert failed_event >= 1


@pytest.mark.asyncio
async def test_check_constraint_rejects_kenny_row_without_source_events(
    postgres_engine: Engine,
) -> None:
    """Direct DB write proves the per scope-v2 §3.1 CHECK constraint is active."""
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)

    with postgres_engine.begin() as c:
        with pytest.raises(Exception) as exc:
            c.execute(
                text(
                    "INSERT INTO matrix_insights "
                    "(tenant_id, engagement_id, agent, insight_type, severity, title, body, dedup_key) "
                    "VALUES (:t, :e, 'kenny', 'decision_provenance_summary', 'medium', "
                    "'no-cites', 'body', :k)"
                ),
                {"t": str(tid), "e": str(eid), "k": f"kenny:test:{uuid.uuid4()}"},
            )
        assert "ck_matrix_insights_source_events_present" in str(exc.value)
