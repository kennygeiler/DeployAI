"""Wave 3 K1 — cold-start demo reset (`POST /internal/v1/admin/demo/reset-acme`).

The demo thesis needs a fresh "Acme Robotics — Pilot Deployment" engagement
between meetings. These tests prove the reset is idempotent, wipes the whole
demo trail (canonical events, proposals, matrix rows, ledger entries), and
recreates the engagement empty under its stable id.
"""

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
from control_plane.api.routes.demo_reset_internal import (
    ACME_ENGAGEMENT_ID,
    ACME_ENGAGEMENT_NAME,
)
from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration

TENANT_ID = uuid.UUID("11111111-1111-4111-8111-aaaaaaaaaaaa")


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'demo-reset-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _count(engine: Engine, table: str, engagement_id: uuid.UUID) -> int:
    with engine.connect() as c:
        r = c.execute(
            text(f"SELECT COUNT(*) FROM {table} WHERE engagement_id = :e"),
            {"e": str(engagement_id)},
        )
        return int(r.scalar_one())


class _FakeLLM:
    """Deterministic extractor stand-in: one node proposal per call."""

    id = "fake"

    def __init__(self, response: str) -> None:
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


@pytest_asyncio.fixture
async def client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "demo-reset-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://test")
    c.headers["X-DeployAI-Internal-Key"] = "demo-reset-test-key"
    try:
        yield c
    finally:
        await c.aclose()
        clear_engine_cache()


@pytest.fixture
def fake_llm() -> Iterator[_FakeLLM]:
    fake = _FakeLLM(
        json.dumps(
            [
                {
                    "kind": "node",
                    "node_type": "decision",
                    "title": "Edge inference for the pilot",
                    "rationale": "Dana called it in the kickoff.",
                }
            ]
        )
    )
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def _reset(client: AsyncClient, tenant_id: uuid.UUID) -> dict:
    r = await client.post(f"/internal/v1/admin/demo/reset-acme?tenant_id={tenant_id}")
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_reset_creates_fresh_engagement(client: AsyncClient, postgres_engine: Engine) -> None:
    _ins_tenant(postgres_engine, TENANT_ID)
    body = await _reset(client, TENANT_ID)
    assert body["engagement_id"] == str(ACME_ENGAGEMENT_ID)
    assert body["engagement_name"] == ACME_ENGAGEMENT_NAME
    assert body["deleted_engagements"] == 0

    r = await client.get(f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}?tenant_id={TENANT_ID}")
    assert r.status_code == 200
    engagement = r.json()
    assert engagement["name"] == ACME_ENGAGEMENT_NAME
    assert engagement["status"] == "active"


@pytest.mark.asyncio
async def test_reset_wipes_demo_trail_and_recreates_empty(
    client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    _ins_tenant(postgres_engine, TENANT_ID)
    await _reset(client, TENANT_ID)

    # Simulate a demo run: ingest one artifact, extract proposals, accept one.
    ingest = await client.post(
        f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}/ingest?tenant_id={TENANT_ID}",
        json={
            "source": "meeting_note",
            "occurred_at": "2026-09-09T17:02:00Z",
            "content": {"text": "Kickoff: Dana decided edge inference for the pilot."},
        },
    )
    assert ingest.status_code == 201, ingest.text
    event_id = ingest.json()["id"]

    extract = await client.post(
        f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}/extract?tenant_id={TENANT_ID}&event_id={event_id}"
    )
    assert extract.status_code == 201, extract.text
    proposals = extract.json()
    assert len(proposals) == 1

    accept = await client.post(
        f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}/proposals/{proposals[0]['id']}/accept?tenant_id={TENANT_ID}",
        json={},
    )
    assert accept.status_code in (200, 201), accept.text

    assert _count(postgres_engine, "canonical_memory_events", ACME_ENGAGEMENT_ID) == 1
    assert _count(postgres_engine, "ledger_events", ACME_ENGAGEMENT_ID) > 0
    assert _count(postgres_engine, "matrix_nodes", ACME_ENGAGEMENT_ID) == 1

    # The reset must clear all of it — including the RESTRICT-FK ledger rows
    # and the append-only canonical events — then recreate the engagement.
    body = await _reset(client, TENANT_ID)
    assert body["deleted_engagements"] == 1
    assert body["deleted_events"] == 1
    assert body["deleted_ledger_events"] > 0

    for table in ("canonical_memory_events", "ledger_events", "matrix_nodes", "matrix_proposals"):
        assert _count(postgres_engine, table, ACME_ENGAGEMENT_ID) == 0, table

    r = await client.get(f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}?tenant_id={TENANT_ID}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reset_wipes_wave5_engagement_scoped_tables(client: AsyncClient, postgres_engine: Engine) -> None:
    """Wave 5 rows (gap-ask dismissals, intake address, Slack mapping) don't break the reset.

    All three tables FK the engagement with ON DELETE CASCADE, but the reset
    wipes them explicitly (see _MANUAL_DELETE_TABLES) so the endpoint never
    silently depends on each new table's FK choice. This test proves the
    reset still succeeds — and clears the rows — once a demo session has
    produced Wave 5 state.
    """
    _ins_tenant(postgres_engine, TENANT_ID)
    await _reset(client, TENANT_ID)

    with postgres_engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO gap_ask_dismissals (tenant_id, engagement_id, ask_id, dismissed_by) "
                "VALUES (:t, :e, 'ask-commitment-no-owner-x', 'demo-guest')"
            ),
            {"t": str(TENANT_ID), "e": str(ACME_ENGAGEMENT_ID)},
        )
        c.execute(
            text(
                "INSERT INTO engagement_intake_addresses (tenant_id, engagement_id, local_part) "
                "VALUES (:t, :e, 'acme-robotics-pilot-deployment-test1234')"
            ),
            {"t": str(TENANT_ID), "e": str(ACME_ENGAGEMENT_ID)},
        )
        c.execute(
            text(
                "INSERT INTO slack_channel_mappings (tenant_id, engagement_id, channel_id, channel_name) "
                "VALUES (:t, :e, 'C0DEM0CHAN', 'fremont-pilot')"
            ),
            {"t": str(TENANT_ID), "e": str(ACME_ENGAGEMENT_ID)},
        )

    for table in ("gap_ask_dismissals", "engagement_intake_addresses", "slack_channel_mappings"):
        assert _count(postgres_engine, table, ACME_ENGAGEMENT_ID) == 1, table

    body = await _reset(client, TENANT_ID)
    assert body["deleted_engagements"] == 1

    for table in ("gap_ask_dismissals", "engagement_intake_addresses", "slack_channel_mappings"):
        assert _count(postgres_engine, table, ACME_ENGAGEMENT_ID) == 0, table

    r = await client.get(f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}?tenant_id={TENANT_ID}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reset_also_removes_same_name_twin(client: AsyncClient, postgres_engine: Engine) -> None:
    """A hand-created engagement with the demo name is cleaned up too."""
    _ins_tenant(postgres_engine, TENANT_ID)
    twin = await client.post(
        f"/internal/v1/engagements?tenant_id={TENANT_ID}",
        json={"name": ACME_ENGAGEMENT_NAME},
    )
    assert twin.status_code == 201, twin.text
    twin_id = twin.json()["id"]
    assert twin_id != str(ACME_ENGAGEMENT_ID)

    body = await _reset(client, TENANT_ID)
    assert body["deleted_engagements"] == 1

    r = await client.get(f"/internal/v1/engagements/{twin_id}?tenant_id={TENANT_ID}")
    assert r.status_code == 404
    r = await client.get(f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}?tenant_id={TENANT_ID}")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_reset_unknown_tenant_404s(client: AsyncClient) -> None:
    r = await client.post(f"/internal/v1/admin/demo/reset-acme?tenant_id={uuid.uuid4()}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_reset_requires_internal_key(client: AsyncClient, postgres_engine: Engine) -> None:
    _ins_tenant(postgres_engine, TENANT_ID)
    r = await client.post(
        f"/internal/v1/admin/demo/reset-acme?tenant_id={TENANT_ID}",
        headers={"X-DeployAI-Internal-Key": "wrong-key"},
    )
    assert r.status_code in (401, 403)
