"""Integration test: Phase 3 adversarial reviewer end-to-end (§7.3).

Concerns alone (no citation fail) → ship reply unchanged + emit ledger
event ``agent_concern_logged`` + persist structured concerns onto
``agent_audit_traces.adversarial_concerns_text``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import CapabilityMatrix, ChatMessage, StreamChunk
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


class _StubLLM:
    """One stub that doubles as the primary + cheap provider.

    ``chat_complete_stream`` serves the agent's main turn(s); the
    adversarial reviewer calls ``chat_complete`` (non-stream) and we
    return :pyattr:`concerns_reply` from there so a single override of
    :func:`get_llm_provider` exercises both code paths.
    """

    id = "phase3-adv-stub"

    def __init__(self, replies: list[str], concerns_reply: str) -> None:
        self._replies = list(replies)
        self.concerns_reply = concerns_reply
        self.calls = 0

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = messages, temperature, max_output_tokens
        return self.concerns_reply

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = messages, temperature, max_output_tokens
        yield self._replies[self.calls] if self.calls < len(self._replies) else ""

    async def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]:
        _ = messages, temperature, max_output_tokens
        idx = self.calls
        self.calls += 1
        body = self._replies[idx] if idx < len(self._replies) else ""
        if body:
            yield StreamChunk(delta=body, done=False, tokens_used=0)
        yield StreamChunk(delta="", done=True, tokens_used=80)

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


def _async_url(engine: Engine) -> str:
    return engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'phase3-adv') ON CONFLICT (id) DO NOTHING"),
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
                "n": f"phase3-adv-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


@pytest_asyncio.fixture
async def k_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "phase3-adv-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "phase3-adv-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.fixture
def stub_factory(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, _StubLLM]]:
    box: dict[str, _StubLLM] = {}

    def _f() -> _StubLLM:
        return box["stub"]

    app.dependency_overrides[get_llm_provider] = _f
    try:
        yield box
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


def _seed_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    summary: str,
) -> uuid.UUID:
    ev = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, source_kind, summary, detail) "
                "VALUES (:id, :t, :e, now(), 'user', 'manual_capture', :s, '{}'::jsonb)"
            ),
            {"id": str(ev), "t": str(tenant_id), "e": str(engagement_id), "s": summary},
        )
    return ev


def _count(engine: Engine, table: str, **filters: Any) -> int:
    where = " AND ".join(f"{k} = :{k}" for k in filters)
    sql = f"SELECT COUNT(*) FROM {table}"
    if where:
        sql += f" WHERE {where}"
    with engine.connect() as c:
        return int(c.execute(text(sql), {k: str(v) for k, v in filters.items()}).scalar_one())


def _actor_headers(user_id: uuid.UUID) -> dict[str, str]:
    return {"X-DeployAI-Actor-Id": str(user_id)}


def _parse_sse_frames(payload: str) -> list[tuple[str, dict[str, Any]]]:
    frames: list[tuple[str, dict[str, Any]]] = []
    for block in payload.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = ""
        data_text = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                data_text = line[len("data: ") :].strip()
        if not event_name:
            continue
        try:
            frames.append((event_name, json.loads(data_text) if data_text else {}))
        except json.JSONDecodeError:
            continue
    return frames


@pytest.mark.asyncio
async def test_phase3_adversarial_concerns_ship_reply_and_log_ledger(
    k_client: AsyncClient,
    postgres_engine: Engine,
    stub_factory: dict[str, _StubLLM],
) -> None:
    """A bait prompt provokes overreach: concerns logged, reply still ships."""
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    user_id = uuid.uuid4()
    _ins_user(postgres_engine, tid, user_id)
    r = await k_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Phase3 adversarial"},
    )
    assert r.status_code == 201
    eng = uuid.UUID(r.json()["id"])

    seed = _seed_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eng,
        summary="real risk surfaced",
    )

    reply = f"Two concerns were raised pre-approval [event:{seed}]."
    concerns_response = (
        "- The reply makes an unstated assumption about pre-approval timing.\n"
        "- Overconfident phrasing about how concerns were resolved.\n"
    )
    stub_factory["stub"] = _StubLLM(replies=[reply], concerns_reply=concerns_response)

    r = await k_client.post(
        f"/internal/v1/engagements/{eng}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "anyone object?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    event_names = [n for n, _ in frames]

    # Reply still shipped (no citation failure → no rejection).
    done = next(p for n, p in frames if n == "done")
    assert str(seed) in done["final_text"]
    assert done["adversarial_concerns"] == 2

    # Each concern surfaced as its own SSE frame BEFORE done.
    concern_indexes = [i for i, n in enumerate(event_names) if n == "adversarial_concern"]
    assert len(concern_indexes) == 2
    assert all(i < event_names.index("done") for i in concern_indexes)
    concern_payloads = [p for n, p in frames if n == "adversarial_concern"]
    severities = {p["severity"] for p in concern_payloads}
    assert "warning" in severities

    # New ledger source kind agent_concern_logged is emitted.
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="agent_concern_logged") == 1
    # The Phase 2 agent_audit_concern ledger event is still emitted too.
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="agent_audit_concern") == 1

    # adversarial_concerns_text JSONB column carries the structured payload.
    with postgres_engine.connect() as c:
        row = c.execute(
            text(
                "SELECT adversarial_concerns_count, adversarial_concerns_text, "
                "verified_concerns_count FROM agent_audit_traces "
                "WHERE tenant_id = :t"
            ),
            {"t": str(tid)},
        ).one()
    assert row[0] == 2
    persisted = row[1]
    assert isinstance(persisted, list)
    assert len(persisted) == 2
    assert {c_["severity"] for c_ in persisted} == {"warning"}
    # No info-only concerns → verified_concerns_count is zero.
    assert row[2] == 0


@pytest.mark.asyncio
async def test_phase3_no_concerns_does_not_emit_concern_logged_ledger(
    k_client: AsyncClient,
    postgres_engine: Engine,
    stub_factory: dict[str, _StubLLM],
) -> None:
    """``NONE`` from the auditor → no agent_concern_logged ledger row."""
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    user_id = uuid.uuid4()
    _ins_user(postgres_engine, tid, user_id)
    r = await k_client.post(
        f"/internal/v1/engagements?tenant_id={tid}",
        json={"name": "Phase3 clean"},
    )
    assert r.status_code == 201
    eng = uuid.UUID(r.json()["id"])
    seed = _seed_event(postgres_engine, tenant_id=tid, engagement_id=eng, summary="clean")
    stub_factory["stub"] = _StubLLM(
        replies=[f"All good [event:{seed}]."],
        concerns_reply="NONE",
    )

    r = await k_client.post(
        f"/internal/v1/engagements/{eng}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "status?"},
        headers=_actor_headers(user_id),
    )
    assert r.status_code == 200, r.text
    assert _count(postgres_engine, "ledger_events", tenant_id=tid, source_kind="agent_concern_logged") == 0
    with postgres_engine.connect() as c:
        row = c.execute(
            text("SELECT adversarial_concerns_text FROM agent_audit_traces WHERE tenant_id = :t"),
            {"t": str(tid)},
        ).one()
    assert row[0] == []
