"""Guest-sandbox wave — per-visitor demo engagements.

``POST /internal/v1/demo/session`` provisions one fresh sandbox engagement
per mint (marked via ``engagements.demo_sandbox_at``), reaps expired ones
opportunistically, and the engagements list can hide foreign sandboxes from
a guest. These tests prove:

- two mints yield two distinct, independently usable cold-start engagements
  (identical artifacts extract in both — no cross-sandbox dedup collision,
  the bug that made visitor #2's capture beats dead);
- the reaper deletes only sandboxes older than the cutoff, bounded per mint,
  and can never touch the seeded fixtures (``demo_sandbox_at IS NULL``);
- the list filter shows a guest the fixtures plus exactly its own sandbox;
- the presenter reset keeps working and never yanks a live guest's sandbox.

Redis is not part of this suite: ``issue_tokens`` is monkeypatched (same as
the unit tests); everything DB-side is real.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Iterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient, Response
from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine

import control_plane.api.routes.demo_session_internal as demo_mod
from control_plane.agents.llm import get_llm_provider
from control_plane.auth.session_service import SessionPair
from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache, tenant_request_session
from control_plane.main import app
from control_plane.services.demo_sandbox import (
    ACME_ENGAGEMENT_ID,
    ACME_ENGAGEMENT_NAME,
    create_demo_engagement,
    reap_expired_sandboxes,
)

pytestmark = pytest.mark.integration

TENANT_ID = uuid.UUID("11111111-1111-4111-8111-bbbbbbbbbbbb")
DEMO_USER_ID = uuid.UUID("44444444-4444-4444-4444-444444444444")
INTERNAL_KEY = "demo-sandbox-test-key"


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'demo-sandbox-test') ON CONFLICT (id) DO NOTHING"),
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
                "n": f"demo-user-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


def _ins_conversation(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: str,
    user_id: uuid.UUID,
    jti: str | None,
    age_hours: int,
) -> uuid.UUID:
    cid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO oracle_conversations "
                "  (id, tenant_id, engagement_id, actor_user_id, demo_session_jti, last_turn_at) "
                "VALUES (CAST(:c AS uuid), CAST(:t AS uuid), CAST(:e AS uuid), CAST(:u AS uuid), "
                "        :jti, now() - make_interval(hours => :h))"
            ),
            {
                "c": str(cid),
                "t": str(tenant_id),
                "e": engagement_id,
                "u": str(user_id),
                "jti": jti,
                "h": age_hours,
            },
        )
    return cid


def _conversation_exists(engine: Engine, cid: uuid.UUID) -> bool:
    with engine.connect() as c:
        return bool(
            c.execute(
                text("SELECT 1 FROM oracle_conversations WHERE id = CAST(:c AS uuid)"),
                {"c": str(cid)},
            ).scalar_one_or_none()
        )


def _backdate_sandbox(engine: Engine, engagement_id: str, hours: int) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "UPDATE engagements SET demo_sandbox_at = now() - make_interval(hours => :h) "
                "WHERE id = CAST(:e AS uuid)"
            ),
            {"h": hours, "e": engagement_id},
        )


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
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", INTERNAL_KEY)
    monkeypatch.setenv("DEPLOYAI_DEMO_GUEST_ENABLED", "1")
    monkeypatch.setenv("DEPLOYAI_DEMO_TENANT_ID", str(TENANT_ID))
    monkeypatch.setenv("DEPLOYAI_DEMO_USER_ID", str(DEMO_USER_ID))
    clear_settings_cache()
    clear_engine_cache()

    # Redis-free: token minting is not under test here.
    async def fake_issue(
        tenant_id: uuid.UUID,
        user_id: uuid.UUID,
        roles: list[str],
        *,
        access_ttl_seconds: int | None = None,
    ) -> SessionPair:
        _ = tenant_id, user_id, roles
        return SessionPair(
            access_token="demo-access-jwt",
            refresh_jti="demo-refresh",
            expires_in=access_ttl_seconds or 900,
        )

    monkeypatch.setattr(demo_mod, "issue_tokens", fake_issue)

    _ins_tenant(postgres_engine, TENANT_ID)
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://test")
    c.headers["X-DeployAI-Internal-Key"] = INTERNAL_KEY
    try:
        yield c
    finally:
        await c.aclose()
        clear_settings_cache()
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


async def _mint(client: AsyncClient) -> dict:
    r = await client.post("/internal/v1/demo/session")
    assert r.status_code == 201, r.text
    return r.json()


async def _get_engagement(client: AsyncClient, engagement_id: str) -> Response:
    return await client.get(f"/internal/v1/engagements/{engagement_id}?tenant_id={TENANT_ID}")


@pytest.mark.asyncio
async def test_two_mints_provision_distinct_sandboxes(client: AsyncClient) -> None:
    a = await _mint(client)
    b = await _mint(client)
    assert a["engagement_id"] != b["engagement_id"]

    for body in (a, b):
        r = await _get_engagement(client, body["engagement_id"])
        assert r.status_code == 200, r.text
        eng = r.json()
        # Same display name for every visitor — the marker, not the name,
        # distinguishes sandboxes from the seeded fixture.
        assert eng["name"] == ACME_ENGAGEMENT_NAME
        assert eng["demo_sandbox_at"] is not None


@pytest.mark.asyncio
async def test_sandboxes_capture_and_extract_independently(client: AsyncClient, fake_llm: _FakeLLM) -> None:
    """Identical artifacts in two sandboxes must extract in BOTH.

    This is the shared-engagement bug the wave fixes: visitor #2 pasting the
    same kickoff transcript used to yield zero proposals (the shared matrix
    already contained the nodes). Fresh per-guest engagements make every
    capture beat live. The ingest carries no dedup_key — mirroring the
    Capture tab flow.
    """
    a = (await _mint(client))["engagement_id"]
    b = (await _mint(client))["engagement_id"]

    for eid in (a, b):
        ingest = await client.post(
            f"/internal/v1/engagements/{eid}/ingest?tenant_id={TENANT_ID}",
            json={
                "source": "meeting_note",
                "occurred_at": "2026-09-09T17:02:00Z",
                "content": {"text": "Kickoff: Dana decided edge inference for the pilot."},
            },
        )
        assert ingest.status_code == 201, ingest.text
        event_id = ingest.json()["id"]

        extract = await client.post(f"/internal/v1/engagements/{eid}/extract?tenant_id={TENANT_ID}&event_id={event_id}")
        assert extract.status_code == 201, extract.text
        proposals = extract.json()
        assert len(proposals) == 1, f"sandbox {eid} got no proposals — dedup collision?"
        assert proposals[0]["engagement_id"] == eid


@pytest.mark.asyncio
async def test_mint_reaps_expired_sandboxes_but_never_fixtures(client: AsyncClient, postgres_engine: Engine) -> None:
    # The stable presenter fixture (demo_sandbox_at NULL)...
    r = await client.post(f"/internal/v1/admin/demo/reset-acme?tenant_id={TENANT_ID}")
    assert r.status_code == 200, r.text

    # ...one sandbox aged past the 24h cutoff, one comfortably fresh.
    expired = (await _mint(client))["engagement_id"]
    fresh = (await _mint(client))["engagement_id"]
    _backdate_sandbox(postgres_engine, expired, hours=25)
    _backdate_sandbox(postgres_engine, fresh, hours=23)

    minted = (await _mint(client))["engagement_id"]

    assert (await _get_engagement(client, expired)).status_code == 404
    assert (await _get_engagement(client, fresh)).status_code == 200
    assert (await _get_engagement(client, minted)).status_code == 200
    # The fixture is never a reap candidate, whatever its age.
    assert (await _get_engagement(client, str(ACME_ENGAGEMENT_ID))).status_code == 200


@pytest.mark.asyncio
async def test_reaper_is_bounded_and_oldest_first(client: AsyncClient, postgres_engine: Engine) -> None:
    _ = client  # env + engine wiring
    ids: list[uuid.UUID] = []
    async with tenant_request_session(TENANT_ID) as session:
        for _i in range(3):
            ids.append(await create_demo_engagement(session, TENANT_ID, sandbox=True))
        await session.commit()
    # Ages: 30h, 28h, 26h — all expired.
    for i, eid in enumerate(ids):
        _backdate_sandbox(postgres_engine, str(eid), hours=30 - 2 * i)

    async with tenant_request_session(TENANT_ID) as session:
        reaped = await reap_expired_sandboxes(session, TENANT_ID, limit=2)
        await session.commit()

    # Bounded work per mint; oldest drain first, the rest wait their turn.
    assert reaped == ids[:2]
    assert (await _get_engagement(client, str(ids[2]))).status_code == 200


@pytest.mark.asyncio
async def test_list_filter_shows_fixtures_plus_own_sandbox_only(client: AsyncClient) -> None:
    r = await client.post(f"/internal/v1/admin/demo/reset-acme?tenant_id={TENANT_ID}")
    assert r.status_code == 200, r.text
    mine = (await _mint(client))["engagement_id"]
    other = (await _mint(client))["engagement_id"]

    async def list_ids(qs: str = "") -> set[str]:
        res = await client.get(f"/internal/v1/engagements?tenant_id={TENANT_ID}{qs}")
        assert res.status_code == 200, res.text
        return {row["id"] for row in res.json()}

    # Unfiltered (real strategist sessions): everything is visible.
    everything = await list_ids()
    assert {str(ACME_ENGAGEMENT_ID), mine, other} <= everything

    # A guest session: fixtures + its own sandbox, never the other visitor's.
    # demo-polish fix 4: the stable presenter Acme (same display name as the
    # guest's sandbox) is hidden too — one Acme row, the guest's own.
    guest = await list_ids(f"&exclude_demo_sandboxes=true&visible_sandbox_id={mine}")
    assert str(ACME_ENGAGEMENT_ID) not in guest
    assert mine in guest
    assert other not in guest

    # Expired cookie (no sandbox id): remaining fixtures only — neither the
    # presenter Acme nor any sandbox.
    no_cookie = await list_ids("&exclude_demo_sandboxes=true")
    assert str(ACME_ENGAGEMENT_ID) not in no_cookie
    assert mine not in no_cookie
    assert other not in no_cookie


@pytest.mark.asyncio
async def test_mint_reaps_stale_demo_conversations_on_fixture_engagements(
    client: AsyncClient, postgres_engine: Engine
) -> None:
    """demo-polish fix 5 — per-guest chat threads on the FIXTURE engagements
    (which the engagement reaper never deletes) are bounded by the mint-time
    conversation reaper: demo threads (demo_session_jti set) older than the
    24h cutoff go; fresh demo threads and normal (jti NULL) conversations
    are never candidates, whatever their age.
    """
    r = await client.post(f"/internal/v1/admin/demo/reset-acme?tenant_id={TENANT_ID}")
    assert r.status_code == 200, r.text
    _ins_user(postgres_engine, TENANT_ID, DEMO_USER_ID)
    fixture = str(ACME_ENGAGEMENT_ID)

    stale_demo = _ins_conversation(
        postgres_engine,
        tenant_id=TENANT_ID,
        engagement_id=fixture,
        user_id=DEMO_USER_ID,
        jti="jti-stale",
        age_hours=25,
    )
    fresh_demo = _ins_conversation(
        postgres_engine,
        tenant_id=TENANT_ID,
        engagement_id=fixture,
        user_id=DEMO_USER_ID,
        jti="jti-fresh",
        age_hours=1,
    )
    old_normal = _ins_conversation(
        postgres_engine,
        tenant_id=TENANT_ID,
        engagement_id=fixture,
        user_id=DEMO_USER_ID,
        jti=None,
        age_hours=100,
    )

    await _mint(client)

    assert not _conversation_exists(postgres_engine, stale_demo)
    assert _conversation_exists(postgres_engine, fresh_demo)
    assert _conversation_exists(postgres_engine, old_normal)


@pytest.mark.asyncio
async def test_reset_acme_preserves_live_sandboxes(client: AsyncClient) -> None:
    """Presenter reset must not kill guest sessions despite the shared name."""
    r = await client.post(f"/internal/v1/admin/demo/reset-acme?tenant_id={TENANT_ID}")
    assert r.status_code == 200, r.text
    sandbox = (await _mint(client))["engagement_id"]

    r = await client.post(f"/internal/v1/admin/demo/reset-acme?tenant_id={TENANT_ID}")
    assert r.status_code == 200, r.text
    body = r.json()
    # Only the fixture itself was recycled — the sandbox (same name, marked)
    # is excluded from the match-by-name sweep.
    assert body["deleted_engagements"] == 1

    assert (await _get_engagement(client, sandbox)).status_code == 200
    assert (await _get_engagement(client, str(ACME_ENGAGEMENT_ID))).status_code == 200
