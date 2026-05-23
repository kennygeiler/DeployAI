"""Sprint 2.2 — /extract-preview integration (no DB writes)."""

from __future__ import annotations

import json
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
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'preview') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


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
        _ = messages, temperature, max_output_tokens
        for chunk in (self.chat_complete(messages),):
            yield chunk

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


@pytest_asyncio.fixture
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "preview-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "preview-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.fixture
def fake_llm() -> Iterator[_FakeLLM]:
    fake = _FakeLLM("[]")
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def _new_engagement(e_client: AsyncClient, postgres_engine: Engine) -> tuple[uuid.UUID, str]:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Preview"})
    return tid, r.json()["id"]


def _row_count(engine: Engine, table: str, tenant_id: uuid.UUID) -> int:
    with engine.connect() as c:
        r = c.execute(text(f"SELECT COUNT(*) FROM {table} WHERE tenant_id = :t"), {"t": str(tenant_id)})
        return int(r.scalar_one())


@pytest.mark.asyncio
async def test_preview_returns_drafts_without_writes(
    e_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    fake_llm.response = json.dumps(
        [
            {
                "kind": "node",
                "node_type": "decision",
                "title": "Phased rollout",
                "rationale": "Team agreed on phasing.",
            },
            {
                "kind": "node",
                "node_type": "risk",
                "title": "Calibration drift",
                "rationale": "Open risk on north corridor.",
            },
        ]
    )
    events_before = _row_count(postgres_engine, "canonical_memory_events", tid)
    proposals_before = _row_count(postgres_engine, "matrix_proposals", tid)

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/extract-preview?tenant_id={tid}",
        json={
            "source": "meeting_note",
            "occurred_at": "2026-05-09T15:00:00+00:00",
            "content": {"text": "Decided phased rollout for week 3. Calibration risk on north corridor."},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    drafts = body["drafts"]
    assert len(drafts) == 2
    titles = {d["payload"]["title"] for d in drafts}
    assert titles == {"Phased rollout", "Calibration drift"}
    assert all(d["kind"] == "node" for d in drafts)
    assert fake_llm.calls == 1

    assert _row_count(postgres_engine, "canonical_memory_events", tid) == events_before
    assert _row_count(postgres_engine, "matrix_proposals", tid) == proposals_before


@pytest.mark.asyncio
async def test_preview_unknown_engagement_404(
    e_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(
        f"/internal/v1/engagements/{uuid.uuid4()}/extract-preview?tenant_id={tid}",
        json={
            "source": "manual_import",
            "occurred_at": "2026-05-09T15:00:00+00:00",
            "content": {"text": "anything"},
        },
    )
    assert r.status_code == 404
    assert fake_llm.calls == 0


@pytest.mark.asyncio
async def test_preview_invalid_source_422(e_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/extract-preview?tenant_id={tid}",
        json={
            "source": "bogus",
            "occurred_at": "2026-05-09T15:00:00+00:00",
            "content": {"text": "x"},
        },
    )
    assert r.status_code == 422
    assert fake_llm.calls == 0


@pytest.mark.asyncio
async def test_preview_empty_drafts_when_llm_returns_empty(
    e_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    fake_llm.response = "[]"
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/extract-preview?tenant_id={tid}",
        json={
            "source": "field_note",
            "occurred_at": "2026-05-09T15:00:00+00:00",
            "content": {"text": "nothing interesting"},
        },
    )
    assert r.status_code == 200
    assert r.json() == {"drafts": []}
    assert _row_count(postgres_engine, "canonical_memory_events", tid) == 0
    assert _row_count(postgres_engine, "matrix_proposals", tid) == 0
