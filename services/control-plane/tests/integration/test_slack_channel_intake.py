"""Integration: Wave 5 SL1 — Slack channel-scoped intake.

Covers the consent boundary end to end:

1. Mapping CRUD — create / list / 409 duplicate / cross-tenant engagement
   404 / idempotent revoke (which discards unflushed staged content).
2. Event flow — mapped-channel messages stage (idempotent under Slack
   re-delivery); unmapped-channel messages are dropped with zero storage;
   the bot joining an unmapped channel records a content-free pending row
   which mapping resolves.
3. Flush — staged messages batch into per-channel-per-day / per-thread
   ``slack.thread`` snapshot events (engagement-scoped), re-flush dedups on
   the fingerprinted key, new messages append a NEW snapshot event (the
   ledger is append-only), and Cartographer extraction chains on each new
   snapshot via the stub-able LLM provider.
4. RLS — the ``deployai_app`` role sees only its tenant's rows on the three
   new tables.
"""

from __future__ import annotations

import json
import os
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from deployai_tenancy import TenantScopedSession
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine

from control_plane.agents.llm import get_llm_provider
from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration

_KEY = "slack-intake-test-key"
_TEAM = "T-SLACK-INTAKE"
_BOT_UID = "U-DEPLOYAI-BOT"


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", _KEY)
    # Dev bypass so tests can POST /integrations/slack/events without signing.
    monkeypatch.setenv("DEPLOYAI_SLACK_ALLOW_UNSIGNED", "1")
    monkeypatch.delenv("DEPLOYAI_SLACK_SIGNING_SECRET", raising=False)
    clear_settings_cache()
    clear_engine_cache()
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://test")
    c.headers["X-DeployAI-Internal-Key"] = _KEY
    try:
        yield c
    finally:
        await c.aclose()
        clear_settings_cache()
        clear_engine_cache()


class _FakeLLM:
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
        _ = temperature, max_output_tokens
        yield self.chat_complete(messages)

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


@pytest.fixture
def fake_llm() -> Iterator[_FakeLLM]:
    fake = _FakeLLM(
        json.dumps(
            [
                {
                    "kind": "node",
                    "node_type": "risk",
                    "title": "Slack thread surfaced a rollout risk",
                    "rationale": "stub extraction from slack.thread snapshot",
                }
            ]
        )
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


def _seed_tenant(engine: Engine, name: str = "slack-intake") -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"), {"t": str(tid), "n": name})
    return tid


def _seed_slack_integration(engine: Engine, tenant_id: uuid.UUID, *, team_id: str = _TEAM) -> None:
    cfg = {"slack": {"team_id": team_id, "team_name": "Test WS"}, "oauth": {"bot_user_id": _BOT_UID}}
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO integrations (tenant_id, provider, display_name, config) "
                "VALUES (:t, 'slack', 'Slack', CAST(:c AS jsonb))"
            ),
            {"t": str(tenant_id), "c": json.dumps(cfg)},
        )


async def _new_engagement(client: AsyncClient, tenant_id: uuid.UUID, name: str = "SL1") -> str:
    r = await client.post(f"/internal/v1/engagements?tenant_id={tenant_id}", json={"name": name})
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


async def _map_channel(
    client: AsyncClient, tenant_id: uuid.UUID, *, channel_id: str, engagement_id: str, name: str = ""
) -> dict[str, Any]:
    r = await client.post(
        f"/internal/v1/slack/channel-mappings?tenant_id={tenant_id}",
        json={"channel_id": channel_id, "channel_name": name, "engagement_id": engagement_id},
    )
    assert r.status_code == 201, r.text
    out: dict[str, Any] = r.json()
    return out


async def _post_message(
    client: AsyncClient, *, channel: str, ts: str, textv: str, thread_ts: str | None = None, user: str = "U1"
) -> dict[str, Any]:
    ev: dict[str, Any] = {"type": "message", "channel": channel, "user": user, "text": textv, "ts": ts}
    if thread_ts is not None:
        ev["thread_ts"] = thread_ts
    r = await client.post(
        "/integrations/slack/events",
        json={"type": "event_callback", "team_id": _TEAM, "event": ev},
    )
    assert r.status_code == 200, r.text
    out: dict[str, Any] = r.json()
    return out


def _count(engine: Engine, table: str, tenant_id: uuid.UUID, extra: str = "") -> int:
    with engine.begin() as conn:
        r = conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t {extra}"),
            {"t": str(tenant_id)},
        )
        return int(r.scalar_one())


# ---------------------------------------------------------------------------
# 1. Mapping CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mapping_crud(client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = await _new_engagement(client, tid)

    m = await _map_channel(client, tid, channel_id="C-CRUD", engagement_id=eid, name="proj-rollout")
    assert m["channel_id"] == "C-CRUD"
    assert m["channel_name"] == "proj-rollout"
    assert m["revoked_at"] is None

    r = await client.get(f"/internal/v1/slack/channel-mappings?tenant_id={tid}")
    assert r.status_code == 200
    assert [x["id"] for x in r.json()] == [m["id"]]

    # Duplicate active mapping → 409.
    r = await client.post(
        f"/internal/v1/slack/channel-mappings?tenant_id={tid}",
        json={"channel_id": "C-CRUD", "engagement_id": eid},
    )
    assert r.status_code == 409

    # Engagement from another tenant → 404.
    tid_b = _seed_tenant(postgres_engine, "slack-intake-b")
    r = await client.post(
        f"/internal/v1/slack/channel-mappings?tenant_id={tid_b}",
        json={"channel_id": "C-OTHER", "engagement_id": eid},
    )
    assert r.status_code == 404

    # Revoke → revoked_at set; second revoke is idempotent; list hides it.
    r = await client.post(f"/internal/v1/slack/channel-mappings/{m['id']}/revoke?tenant_id={tid}")
    assert r.status_code == 200
    assert r.json()["revoked_at"] is not None
    r2 = await client.post(f"/internal/v1/slack/channel-mappings/{m['id']}/revoke?tenant_id={tid}")
    assert r2.status_code == 200
    assert r2.json()["revoked_at"] == r.json()["revoked_at"]
    r = await client.get(f"/internal/v1/slack/channel-mappings?tenant_id={tid}")
    assert r.json() == []
    r = await client.get(f"/internal/v1/slack/channel-mappings?tenant_id={tid}&include_revoked=true")
    assert len(r.json()) == 1

    # Re-mapping the channel after revoke is allowed (new consent grant).
    await _map_channel(client, tid, channel_id="C-CRUD", engagement_id=eid)


# ---------------------------------------------------------------------------
# 2. Event flow: staging, drop, pending
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_mapped_channel_stages_and_redelivery_dedups(client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    _seed_slack_integration(postgres_engine, tid)
    eid = await _new_engagement(client, tid)
    await _map_channel(client, tid, channel_id="C-MAPPED", engagement_id=eid)

    out = await _post_message(client, channel="C-MAPPED", ts="1755075000.000100", textv="kickoff at 10")
    assert out["action"] == "staged"
    # Slack re-delivery of the same event → deduped, still one row.
    out = await _post_message(client, channel="C-MAPPED", ts="1755075000.000100", textv="kickoff at 10")
    assert out["action"] == "deduped"
    assert _count(postgres_engine, "slack_staging_messages", tid) == 1
    # Nothing canonical at event time — snapshots only land on flush.
    assert _count(postgres_engine, "canonical_memory_events", tid, "AND event_type LIKE 'slack%'") == 0


@pytest.mark.asyncio
async def test_unmapped_channel_messages_are_dropped_without_storage(
    client: AsyncClient, postgres_engine: Engine
) -> None:
    tid = _seed_tenant(postgres_engine)
    _seed_slack_integration(postgres_engine, tid)

    out = await _post_message(client, channel="C-UNMAPPED", ts="1755075001.000100", textv="secret stuff")
    assert out["action"] == "dropped"
    assert out["reason"] == "unmapped_channel"
    assert _count(postgres_engine, "slack_staging_messages", tid) == 0
    assert _count(postgres_engine, "canonical_memory_events", tid) == 0


@pytest.mark.asyncio
async def test_bot_join_records_pending_channel_and_mapping_resolves_it(
    client: AsyncClient, postgres_engine: Engine
) -> None:
    tid = _seed_tenant(postgres_engine)
    _seed_slack_integration(postgres_engine, tid)

    r = await client.post(
        "/integrations/slack/events",
        json={
            "type": "event_callback",
            "team_id": _TEAM,
            "event": {"type": "member_joined_channel", "user": _BOT_UID, "channel": "C-NEW"},
        },
    )
    assert r.status_code == 200
    assert r.json()["action"] == "pending_channel"
    # Re-delivery keeps a single pending row.
    await client.post(
        "/integrations/slack/events",
        json={
            "type": "event_callback",
            "team_id": _TEAM,
            "event": {"type": "member_joined_channel", "user": _BOT_UID, "channel": "C-NEW"},
        },
    )
    r = await client.get(f"/internal/v1/slack/pending-channels?tenant_id={tid}")
    assert [p["channel_id"] for p in r.json()] == ["C-NEW"]

    # A human joining is not consent-relevant → no pending row.
    r = await client.post(
        "/integrations/slack/events",
        json={
            "type": "event_callback",
            "team_id": _TEAM,
            "event": {"type": "member_joined_channel", "user": "U-HUMAN", "channel": "C-HUMAN"},
        },
    )
    assert r.json()["action"] == "ok"
    assert _count(postgres_engine, "slack_pending_channels", tid) == 1

    # Mapping the channel resolves the pending offer.
    eid = await _new_engagement(client, tid)
    await _map_channel(client, tid, channel_id="C-NEW", engagement_id=eid)
    r = await client.get(f"/internal/v1/slack/pending-channels?tenant_id={tid}")
    assert r.json() == []


# ---------------------------------------------------------------------------
# 3. Flush: snapshots + idempotency + extraction chain
# ---------------------------------------------------------------------------


def _snapshot_rows(engine: Engine, tenant_id: uuid.UUID) -> list[dict[str, Any]]:
    with engine.begin() as conn:
        rows = conn.execute(
            text(
                "SELECT id, engagement_id, source_ref, payload FROM canonical_memory_events "
                "WHERE tenant_id = :t AND event_type = 'slack.thread' ORDER BY source_ref"
            ),
            {"t": str(tenant_id)},
        ).mappings()
        return [dict(r) for r in rows]


@pytest.mark.asyncio
async def test_flush_batches_day_and_thread_units_and_chains_extraction(
    client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid = _seed_tenant(postgres_engine)
    _seed_slack_integration(postgres_engine, tid)
    eid = await _new_engagement(client, tid)
    await _map_channel(client, tid, channel_id="C-FLUSH", engagement_id=eid, name="proj-x")

    # Two plain messages (same UTC day) + two messages in one thread.
    await _post_message(client, channel="C-FLUSH", ts="1755075000.000100", textv="plain one")
    await _post_message(client, channel="C-FLUSH", ts="1755075060.000200", textv="plain two")
    await _post_message(
        client, channel="C-FLUSH", ts="1755075100.000300", textv="thread root", thread_ts="1755075100.000300"
    )
    await _post_message(
        client, channel="C-FLUSH", ts="1755075200.000400", textv="thread reply", thread_ts="1755075100.000300"
    )

    r = await client.post(f"/internal/v1/slack/flush?tenant_id={tid}")
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["snapshots_written"] == 2  # one day unit + one thread unit
    assert rep["messages_flushed"] == 4
    assert rep["extraction_errors"] == []

    snaps = _snapshot_rows(postgres_engine, tid)
    assert len(snaps) == 2
    for s in snaps:
        assert str(s["engagement_id"]) == eid
    day_snap = next(s for s in snaps if s["payload"]["unit"].startswith("d"))
    thread_snap = next(s for s in snaps if s["payload"]["unit"].startswith("t"))
    assert [m["text"] for m in day_snap["payload"]["messages"]] == ["plain one", "plain two"]
    assert [m["text"] for m in thread_snap["payload"]["messages"]] == ["thread root", "thread reply"]

    # Extraction chained once per new snapshot; proposals cite the snapshot.
    assert fake_llm.calls == 2
    with postgres_engine.begin() as conn:
        n = conn.execute(
            text("SELECT count(*) FROM matrix_proposals WHERE tenant_id = :t"),
            {"t": str(tid)},
        ).scalar_one()
    assert int(n) == 2

    # Re-flush with no new messages: everything already flushed → no-op.
    r = await client.post(f"/internal/v1/slack/flush?tenant_id={tid}")
    rep = r.json()
    assert rep["snapshots_written"] == 0
    assert rep["messages_flushed"] == 0
    assert fake_llm.calls == 2
    assert len(_snapshot_rows(postgres_engine, tid)) == 2

    # A new message in the day unit → a NEW snapshot event containing the
    # whole unit (append-only supersede, never mutation).
    await _post_message(client, channel="C-FLUSH", ts="1755075120.000500", textv="plain three")
    r = await client.post(f"/internal/v1/slack/flush?tenant_id={tid}")
    rep = r.json()
    assert rep["snapshots_written"] == 1
    snaps = _snapshot_rows(postgres_engine, tid)
    assert len(snaps) == 3
    texts = sorted(
        tuple(m["text"] for m in s["payload"]["messages"]) for s in snaps if s["payload"]["unit"].startswith("d")
    )
    assert texts == [("plain one", "plain two"), ("plain one", "plain two", "plain three")]


@pytest.mark.asyncio
async def test_flush_is_idempotent_under_staging_redelivery(
    client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid = _seed_tenant(postgres_engine)
    _seed_slack_integration(postgres_engine, tid)
    eid = await _new_engagement(client, tid)
    await _map_channel(client, tid, channel_id="C-IDEM", engagement_id=eid)

    await _post_message(client, channel="C-IDEM", ts="1755075000.000100", textv="hello")
    r = await client.post(f"/internal/v1/slack/flush?tenant_id={tid}")
    assert r.json()["snapshots_written"] == 1

    # Slack re-delivers the same message after the flush: staging dedups it,
    # so the unit is unchanged and a re-flush writes nothing new.
    out = await _post_message(client, channel="C-IDEM", ts="1755075000.000100", textv="hello")
    assert out["action"] == "deduped"
    r = await client.post(f"/internal/v1/slack/flush?tenant_id={tid}")
    assert r.json()["snapshots_written"] == 0
    assert len(_snapshot_rows(postgres_engine, tid)) == 1


@pytest.mark.asyncio
async def test_revoke_discards_unflushed_staged_messages(
    client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid = _seed_tenant(postgres_engine)
    _seed_slack_integration(postgres_engine, tid)
    eid = await _new_engagement(client, tid)
    m = await _map_channel(client, tid, channel_id="C-REVOKE", engagement_id=eid)

    await _post_message(client, channel="C-REVOKE", ts="1755075000.000100", textv="pre-revoke")
    assert _count(postgres_engine, "slack_staging_messages", tid) == 1

    r = await client.post(f"/internal/v1/slack/channel-mappings/{m['id']}/revoke?tenant_id={tid}")
    assert r.status_code == 200
    # Consent withdrawn: unflushed staged content is gone, nothing canonical.
    assert _count(postgres_engine, "slack_staging_messages", tid) == 0
    r = await client.post(f"/internal/v1/slack/flush?tenant_id={tid}")
    assert r.json()["snapshots_written"] == 0
    assert _snapshot_rows(postgres_engine, tid) == []


# ---------------------------------------------------------------------------
# 4. RLS cross-tenant isolation on the new tables
# ---------------------------------------------------------------------------

_APP_USER = "deployai_app"
_APP_PASSWORD = os.environ.get("FUZZ_APP_PASSWORD") or "deployai-fuzz-test"


@pytest.mark.asyncio
async def test_rls_blocks_cross_tenant_reads_on_slack_tables(client: AsyncClient, postgres_engine: Engine) -> None:
    tid_a = _seed_tenant(postgres_engine, "slack-rls-a")
    tid_b = _seed_tenant(postgres_engine, "slack-rls-b")
    _seed_slack_integration(postgres_engine, tid_a)
    eid = await _new_engagement(client, tid_a)
    await _map_channel(client, tid_a, channel_id="C-RLS", engagement_id=eid)
    await _post_message(client, channel="C-RLS", ts="1755075000.000100", textv="tenant A only")
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO slack_pending_channels (tenant_id, channel_id, channel_name) "
                "VALUES (:t, 'C-PENDING', 'a-pending')"
            ),
            {"t": str(tid_a)},
        )
        conn.execute(text(f"ALTER ROLE {_APP_USER} WITH LOGIN PASSWORD '{_APP_PASSWORD}'"))

    app_url = postgres_engine.url.set(
        drivername="postgresql+psycopg", username=_APP_USER, password=_APP_PASSWORD
    ).render_as_string(hide_password=False)
    eng = create_async_engine(app_url)
    tables = ("slack_channel_mappings", "slack_staging_messages", "slack_pending_channels")
    try:
        async with TenantScopedSession(tid_a, eng) as s_a:
            for t in tables:
                n = (await s_a.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one()
                assert int(n) == 1, f"tenant A should see its own {t} row"
        async with TenantScopedSession(tid_b, eng) as s_b:
            for t in tables:
                n = (await s_b.execute(text(f"SELECT count(*) FROM {t}"))).scalar_one()
                assert int(n) == 0, f"tenant B must not see tenant A's {t} rows"
    finally:
        await eng.dispose()
