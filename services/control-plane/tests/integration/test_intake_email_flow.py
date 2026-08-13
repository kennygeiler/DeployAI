"""Inbound engagement email intake (Wave 5 IN1) — webhook → event → extraction.

Covers the verification bar for the intake lane: the full chain with a stub
LLM, unknown/revoked-address drops, redelivery dedup, the per-address rate
limit, and regenerate revoking the old address.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

import control_plane.api.routes.intake_email_internal as intake_route_mod
from control_plane.agents.llm import get_llm_provider
from control_plane.api.routes.intake_email_internal import reset_intake_rate_limiter_state
from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.main import app

from .test_engagements_internal import _FakeLLM, _ins_tenant

pytestmark = pytest.mark.integration

INTERNAL_KEY = "intake-int-key"
INTAKE_SECRET = "intake-webhook-secret"


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def i_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", INTERNAL_KEY)
    monkeypatch.setenv("DEPLOYAI_INTAKE_WEBHOOK_SECRET", INTAKE_SECRET)
    monkeypatch.setenv("DEPLOYAI_INTAKE_EMAIL_DOMAIN", "intake.test.deployai")
    # Force the in-memory per-address limiter (no Redis in this suite).
    monkeypatch.delenv("DEPLOYAI_REDIS_URL", raising=False)
    clear_settings_cache()
    clear_engine_cache()
    reset_intake_rate_limiter_state()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = INTERNAL_KEY
    try:
        yield client
    finally:
        await client.aclose()
        reset_intake_rate_limiter_state()
        clear_settings_cache()
        clear_engine_cache()


@pytest.fixture
def fake_llm() -> Iterator[_FakeLLM]:
    fake = _FakeLLM("[]")
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def _new_engagement(client: AsyncClient, engine: Engine, name: str = "Acme Rollout") -> tuple[uuid.UUID, str]:
    tid = uuid.uuid4()
    _ins_tenant(engine, tid)
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": name})
    assert r.status_code == 201, r.text
    return tid, str(r.json()["id"])


async def _intake_address(client: AsyncClient, tid: uuid.UUID, eid: str) -> dict[str, object]:
    r = await client.get(f"/internal/v1/engagements/{eid}/intake-address?tenant_id={tid}")
    assert r.status_code == 200, r.text
    body: dict[str, object] = r.json()
    return body


def _postmark_payload(
    local_part: str, *, message_id: str = "msg-1", text_body: str = "Decided to phase it."
) -> dict[str, object]:
    return {
        "From": "buyer@example.com",
        "To": f"Deal <{local_part}@intake.test.deployai>, someone@else.example",
        "ToFull": [
            {"Email": f"{local_part}@intake.test.deployai", "Name": "Deal"},
            {"Email": "someone@else.example", "Name": ""},
        ],
        "Subject": "Re: rollout plan",
        "TextBody": text_body,
        "HtmlBody": "<p>ignored when TextBody present</p>",
        "MessageID": message_id,
        "Date": "Wed, 12 Aug 2026 10:30:00 +0000",
        "Attachments": [{"Name": "ignored.pdf", "Content": "…"}],
    }


async def _post_webhook(client: AsyncClient, payload: dict[str, object]) -> dict[str, object]:
    r = await client.post(
        "/internal/v1/intake/email",
        headers={"X-DeployAI-Intake-Secret": INTAKE_SECRET},
        json=payload,
    )
    assert r.status_code == 200, r.text
    body: dict[str, object] = r.json()
    return body


@pytest.mark.asyncio
async def test_address_is_minted_lazily_and_stable(i_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(i_client, postgres_engine, name="NYC DOT LiDAR")
    first = await _intake_address(i_client, tid, eid)
    lp = str(first["local_part"])
    assert lp.startswith("nyc-dot-lidar-")
    assert len(lp.rsplit("-", 1)[-1]) >= 16
    assert first["email"] == f"{lp}@intake.test.deployai"
    # Second read returns the same address, not a new mint.
    second = await _intake_address(i_client, tid, eid)
    assert second["local_part"] == lp


@pytest.mark.asyncio
async def test_webhook_chains_event_and_extraction(
    i_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid = await _new_engagement(i_client, postgres_engine)
    addr = await _intake_address(i_client, tid, eid)
    lp = str(addr["local_part"])

    fake_llm.response = json.dumps(
        [{"kind": "node", "node_type": "decision", "title": "Phased rollout", "rationale": "email said so"}]
    )
    out = await _post_webhook(i_client, _postmark_payload(lp))
    assert out["dropped"] is False
    assert out["deduplicated"] is False
    assert out["extract_error"] is None
    event_id = str(out["event_id"])

    # Canonical event landed on the engagement as email.thread.
    with postgres_engine.begin() as c:
        row = c.execute(
            text("SELECT event_type, engagement_id, payload FROM canonical_memory_events WHERE id = CAST(:i AS uuid)"),
            {"i": event_id},
        ).one()
    assert row[0] == "email.thread"
    assert str(row[1]) == eid
    payload = row[2]
    assert payload["subject"] == "Re: rollout plan"
    assert payload["from"] == "buyer@example.com"
    assert payload["text"] == "Decided to phase it."

    # Extraction chained: one proposal citing the event.
    r = await i_client.get(f"/internal/v1/engagements/{eid}/proposals?tenant_id={tid}")
    proposals = r.json()
    assert len(proposals) == 1
    assert proposals[0]["source_event_id"] == event_id
    assert fake_llm.calls == 1

    # Audit: intake_email_received ledger row referencing the event.
    with postgres_engine.begin() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM ledger_events WHERE source_kind = 'intake_email_received' "
                "AND source_ref = CAST(:i AS uuid)"
            ),
            {"i": event_id},
        ).scalar_one()
    assert n == 1


@pytest.mark.asyncio
async def test_webhook_unknown_address_drops_with_200(i_client: AsyncClient) -> None:
    out = await _post_webhook(i_client, _postmark_payload("no-such-address-abcdefghijklmnop"))
    assert out == {"dropped": True, "reason": "unknown_address"}


@pytest.mark.asyncio
async def test_webhook_redelivery_dedups(i_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM) -> None:
    tid, eid = await _new_engagement(i_client, postgres_engine)
    lp = str((await _intake_address(i_client, tid, eid))["local_part"])

    first = await _post_webhook(i_client, _postmark_payload(lp, message_id="msg-dup"))
    second = await _post_webhook(i_client, _postmark_payload(lp, message_id="msg-dup"))
    assert first["deduplicated"] is False
    assert second["deduplicated"] is True
    assert second["event_id"] == first["event_id"]
    # Redelivery re-runs neither the event write nor the extraction.
    assert fake_llm.calls == 1
    with postgres_engine.begin() as c:
        n = c.execute(
            text("SELECT count(*) FROM canonical_memory_events WHERE tenant_id = CAST(:t AS uuid)"),
            {"t": str(tid)},
        ).scalar_one()
    assert n == 1


@pytest.mark.asyncio
async def test_webhook_oversize_drops(i_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM) -> None:
    tid, eid = await _new_engagement(i_client, postgres_engine)
    lp = str((await _intake_address(i_client, tid, eid))["local_part"])
    out = await _post_webhook(i_client, _postmark_payload(lp, text_body="x" * 500_001))
    assert out == {"dropped": True, "reason": "oversize"}
    assert fake_llm.calls == 0


@pytest.mark.asyncio
async def test_webhook_rate_limit_drops_after_budget(
    i_client: AsyncClient,
    postgres_engine: Engine,
    fake_llm: _FakeLLM,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(intake_route_mod, "RATE_LIMIT_PER_HOUR", 2)
    tid, eid = await _new_engagement(i_client, postgres_engine)
    lp = str((await _intake_address(i_client, tid, eid))["local_part"])

    a = await _post_webhook(i_client, _postmark_payload(lp, message_id="m-1"))
    b = await _post_webhook(i_client, _postmark_payload(lp, message_id="m-2"))
    c = await _post_webhook(i_client, _postmark_payload(lp, message_id="m-3"))
    assert a["dropped"] is False
    assert b["dropped"] is False
    assert c == {"dropped": True, "reason": "rate_limited"}


@pytest.mark.asyncio
async def test_regenerate_revokes_old_address(
    i_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid = await _new_engagement(i_client, postgres_engine)
    old_lp = str((await _intake_address(i_client, tid, eid))["local_part"])

    r = await i_client.post(
        f"/internal/v1/engagements/{eid}/intake-address/regenerate?tenant_id={tid}",
        json={"actor_id": "admin-1"},
    )
    assert r.status_code == 201, r.text
    new_lp = str(r.json()["local_part"])
    assert new_lp != old_lp

    # The read now serves the new address…
    assert str((await _intake_address(i_client, tid, eid))["local_part"]) == new_lp
    # …the old one is recognizably revoked (still a 200 drop, never a bounce)…
    out_old = await _post_webhook(i_client, _postmark_payload(old_lp))
    assert out_old == {"dropped": True, "reason": "revoked_address"}
    # …and the new one works.
    out_new = await _post_webhook(i_client, _postmark_payload(new_lp))
    assert out_new["dropped"] is False

    # Audit row for the rotation.
    with postgres_engine.begin() as c:
        n = c.execute(
            text(
                "SELECT count(*) FROM ledger_events WHERE source_kind = 'intake_address_regenerated' "
                "AND tenant_id = CAST(:t AS uuid)"
            ),
            {"t": str(tid)},
        ).scalar_one()
    assert n == 1


@pytest.mark.asyncio
async def test_address_routes_require_internal_key(i_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(i_client, postgres_engine)
    bare = AsyncClient(transport=ASGITransport(app=app), base_url="http://test")
    try:
        r = await bare.get(f"/internal/v1/engagements/{eid}/intake-address?tenant_id={tid}")
        assert r.status_code == 401
    finally:
        await bare.aclose()
