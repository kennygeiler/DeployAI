"""Mr. Oracle chat internal API — integration tests (Phase G1.a)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime, timedelta
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
from control_plane.domain.llm_budget import DEFAULT_DAILY_CAP
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'oracle-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_user(engine: Engine, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO app_users (id, tenant_id, user_name, email) "
                "VALUES (:u, :t, :n, :e) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "u": str(user_id),
                "t": str(tenant_id),
                "n": f"oracle-tester-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


class _FakeLLM:
    id = "fake"

    def __init__(self, response: str = "Oracle reply. Cited [event:abc].") -> None:
        self.response = response
        self.calls = 0
        self.last_messages: list[ChatMessage] | None = None

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = temperature, max_output_tokens
        self.calls += 1
        self.last_messages = messages
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


@pytest_asyncio.fixture
async def o_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "oracle-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "oracle-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.fixture
def fake_llm() -> Iterator[_FakeLLM]:
    fake = _FakeLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def _new_engagement(client: AsyncClient, engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tid = uuid.uuid4()
    _ins_tenant(engine, tid)
    user_id = uuid.uuid4()
    _ins_user(engine, tid, user_id)
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Oracle test"})
    assert r.status_code == 201, r.text
    return tid, uuid.UUID(r.json()["id"]), user_id


def _seed_ledger_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    source_kind: str,
    summary: str,
    occurred_at: datetime | None = None,
) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id, "
                "source_kind, source_ref, summary, detail) "
                "VALUES (:id, :t, :e, :occ, 'user', NULL, :sk, NULL, :sum, '{}'::jsonb)"
            ),
            {
                "id": str(eid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "occ": occurred_at or datetime.now(UTC) - timedelta(hours=1),
                "sk": source_kind,
                "sum": summary,
            },
        )
    return eid


def _count(engine: Engine, table: str, **filters: Any) -> int:
    where = " AND ".join(f"{k} = :{k}" for k in filters)
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with engine.connect() as c:
        return int(c.execute(text(sql), {k: str(v) for k, v in filters.items()}).scalar_one())


def _actor_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"X-DeployAI-Actor-Id": str(user_id)}


@pytest.mark.asyncio
async def test_start_new_conversation_writes_row_and_emits_started_event(
    o_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid, user_id = await _new_engagement(o_client, postgres_engine)

    r = await o_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat?tenant_id={tid}",
        json={"conversation_id": None, "message": "Where are we on phasing?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["content"]
    assert body["tokens_used"] > 0

    assert _count(postgres_engine, "oracle_conversations", tenant_id=tid, engagement_id=eid) == 1
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="oracle_conversation_started") == 1


@pytest.mark.asyncio
async def test_send_message_persists_two_turns_and_emits_dual_ledger_event(
    o_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid, user_id = await _new_engagement(o_client, postgres_engine)
    upstream = _seed_ledger_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        source_kind="proposal_accepted",
        summary="accept decision: phased rollout",
    )

    r = await o_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat?tenant_id={tid}",
        json={"conversation_id": None, "message": "Why phased rollout?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    body = r.json()

    assert fake_llm.calls == 1
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 2

    with postgres_engine.connect() as c:
        roles = [
            row[0]
            for row in c.execute(
                text("SELECT role FROM oracle_chat_turns WHERE tenant_id = :t ORDER BY created_at"),
                {"t": str(tid)},
            )
        ]
        assert roles == ["user", "oracle"]

        chat_turn_event = c.execute(
            text("SELECT id FROM ledger_events WHERE tenant_id = :t AND source_kind = 'oracle_chat_turn'"),
            {"t": str(tid)},
        ).scalar_one()

        causes = [
            row[0]
            for row in c.execute(
                text("SELECT caused_by_id FROM ledger_event_causes WHERE event_id = :e"),
                {"e": str(chat_turn_event)},
            )
        ]
        assert uuid.UUID(str(upstream)) in [uuid.UUID(str(x)) for x in causes]

    # echo conversation id back enables threading on the next turn
    second = await o_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat?tenant_id={tid}",
        json={"conversation_id": body["conversation_id"], "message": "Follow-up"},
        headers=_actor_headers(user_id),
    )
    assert second.status_code == 200, second.text
    assert _count(postgres_engine, "oracle_conversations", tenant_id=tid, engagement_id=eid) == 1
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 4


@pytest.mark.asyncio
async def test_budget_exhausted_returns_429_and_writes_nothing(
    o_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid, user_id = await _new_engagement(o_client, postgres_engine)
    today = datetime.now(UTC).date()
    with postgres_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO tenant_llm_daily_budget (tenant_id, usage_date, tokens_used, daily_cap) "
                "VALUES (:t, :d, :u, :c)"
            ),
            {"t": str(tid), "d": today, "u": DEFAULT_DAILY_CAP, "c": DEFAULT_DAILY_CAP},
        )

    r = await o_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat?tenant_id={tid}",
        json={"conversation_id": None, "message": "hi"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 429, r.text
    detail = r.json()["detail"]
    assert detail["error"] == "daily LLM budget exhausted"
    assert "retry_after_iso" in detail
    assert fake_llm.calls == 0
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid) == 0


@pytest.mark.asyncio
async def test_cross_tenant_engagement_returns_404(
    o_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    # tenant A owns an engagement; tenant B asks for it via the URL — must 404.
    tid_a, eid_a, _user_a = await _new_engagement(o_client, postgres_engine)
    tid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_b)
    user_b = uuid.uuid4()
    _ins_user(postgres_engine, tid_b, user_b)

    r = await o_client.post(
        f"/internal/v1/engagements/{eid_a}/oracle/chat?tenant_id={tid_b}",
        json={"conversation_id": None, "message": "leak attempt"},
        headers=_actor_headers(user_b),
    )
    assert r.status_code == 404, r.text
    assert fake_llm.calls == 0
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid_a) == 0
    assert _count(postgres_engine, "oracle_chat_turns", tenant_id=tid_b) == 0


@pytest.mark.asyncio
async def test_history_endpoint_returns_turns_in_order(
    o_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid, user_id = await _new_engagement(o_client, postgres_engine)
    r = await o_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat?tenant_id={tid}",
        json={"conversation_id": None, "message": "ping"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text

    h = await o_client.get(
        f"/internal/v1/engagements/{eid}/oracle/history?tenant_id={tid}",
        headers=_actor_headers(user_id),
    )
    assert h.status_code == 200, h.text
    body = h.json()
    assert body["conversation_id"] is not None
    assert [t["role"] for t in body["turns"]] == ["user", "oracle"]
    assert body["turns"][0]["content"] == "ping"


def test_migration_round_trip_drops_oracle_tables_clean(postgres_engine: Engine) -> None:
    """0040 down → up leaves no leftover tables and restores the indexes.

    Runs synchronously (not pytest-asyncio) because alembic's command API
    is sync and we want the session-scoped engine left at HEAD on exit.
    """
    from pathlib import Path

    from alembic.config import Config

    from alembic import command

    service_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(service_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(service_root / "alembic"))
    cfg.set_main_option(
        "sqlalchemy.url",
        postgres_engine.url.render_as_string(hide_password=False),
    )

    def _has_table(name: str) -> bool:
        with postgres_engine.connect() as c:
            return bool(
                c.execute(
                    text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = :n"),
                    {"n": name},
                ).scalar_one_or_none()
            )

    assert _has_table("oracle_conversations")
    assert _has_table("oracle_chat_turns")

    command.downgrade(cfg, "20260613_0039")
    try:
        assert not _has_table("oracle_conversations")
        assert not _has_table("oracle_chat_turns")
    finally:
        command.upgrade(cfg, "head")

    assert _has_table("oracle_conversations")
    assert _has_table("oracle_chat_turns")
