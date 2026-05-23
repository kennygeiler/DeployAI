"""Tenants internal API (integration) — Phase 7.4 Master Strategist."""

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


@pytest_asyncio.fixture
async def t_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "t-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "t-test-key"
    try:
        yield client
    finally:
        await client.aclose()
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


# --- helpers ----------------------------------------------------------------


def _seed_tenant_and_engagement(
    engine: Engine, *, name: str, roles: tuple[str, ...] = ()
) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert tenant + engagement + optional members; return (tenant_id, engagement_id)."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, :n) ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid), "n": "tenants-test"},
        )
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:e, :t, :n, 'discovery', 'active')"
            ),
            {"e": str(eid), "t": str(tid), "n": name},
        )
        for role in roles:
            uid = uuid.uuid4()
            conn.execute(
                text("INSERT INTO app_users (id, tenant_id, user_name) VALUES (:u, :t, :n)"),
                {"u": str(uid), "t": str(tid), "n": f"user-{role}"},
            )
            conn.execute(
                text(
                    "INSERT INTO engagement_members (tenant_id, engagement_id, user_id, role) VALUES (:t, :e, :u, :r)"
                ),
                {"t": str(tid), "e": str(eid), "u": str(uid), "r": role},
            )
    return tid, eid


def _add_engagement(engine: Engine, tid: uuid.UUID, *, name: str, roles: tuple[str, ...] = ()) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:e, :t, :n, 'discovery', 'active')"
            ),
            {"e": str(eid), "t": str(tid), "n": name},
        )
        for role in roles:
            uid = uuid.uuid4()
            conn.execute(
                text("INSERT INTO app_users (id, tenant_id, user_name) VALUES (:u, :t, :n)"),
                {"u": str(uid), "t": str(tid), "n": f"user-{role}-{name}"},
            )
            conn.execute(
                text(
                    "INSERT INTO engagement_members (tenant_id, engagement_id, user_id, role) VALUES (:t, :e, :u, :r)"
                ),
                {"t": str(tid), "e": str(eid), "u": str(uid), "r": role},
            )
    return eid


def _seed_node(
    engine: Engine,
    tid: uuid.UUID,
    eid: uuid.UUID,
    *,
    node_type: str,
    title: str,
) -> uuid.UUID:
    with engine.begin() as conn:
        nid = conn.execute(
            text(
                "INSERT INTO matrix_nodes (tenant_id, engagement_id, node_type, title) "
                "VALUES (:t, :e, :nt, :title) RETURNING id"
            ),
            {"t": str(tid), "e": str(eid), "nt": node_type, "title": title},
        ).scalar_one()
    return nid


# --- tests -------------------------------------------------------------------


@pytest.mark.asyncio
async def test_refresh_no_engagements_returns_empty_skips_llm(
    t_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    # Tenant exists but has no engagements yet.
    tid = uuid.uuid4()
    with postgres_engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'lonely')"),
            {"t": str(tid)},
        )
    r = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    assert r.status_code == 200
    assert r.json() == []
    assert fake_llm.calls == 0


@pytest.mark.asyncio
async def test_refresh_recurring_risk_creates_open_insight(
    t_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid_a = _seed_tenant_and_engagement(postgres_engine, name="A")
    eid_b = _add_engagement(postgres_engine, tid, name="B")
    _seed_node(postgres_engine, tid, eid_a, node_type="risk", title="data residency")
    _seed_node(postgres_engine, tid, eid_b, node_type="risk", title="data residency concerns")
    fake_llm.response = json.dumps([{"title": "Recurring data-residency risk", "body": "Both."}])
    r = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    assert r.status_code == 200, r.text
    insights = r.json()
    assert len(insights) == 1
    i = insights[0]
    assert i["insight_type"] == "recurring_risk_pattern"
    assert i["engagement_id"] is None
    assert i["agent"] == "master_strategist"
    assert i["status"] == "open"


@pytest.mark.asyncio
async def test_refresh_role_coverage_gap_one_per_role(
    t_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, _eid_a = _seed_tenant_and_engagement(
        postgres_engine, name="A", roles=("deployment_strategist", "fde", "biz_dev")
    )
    _add_engagement(postgres_engine, tid, name="B", roles=("deployment_strategist", "fde", "biz_dev"))
    _add_engagement(postgres_engine, tid, name="C", roles=("deployment_strategist",))
    fake_llm.response = json.dumps(
        [
            {"title": "C is missing an FDE", "body": "Other engagements have one."},
            {"title": "C is missing a biz-dev lead", "body": "Other engagements have one."},
        ]
    )
    r = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    assert r.status_code == 200
    insights = r.json()
    types = sorted(i["insight_type"] for i in insights)
    assert types == ["role_coverage_gap", "role_coverage_gap"]


@pytest.mark.asyncio
async def test_unchanged_inputs_short_circuit_llm(
    t_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid_a = _seed_tenant_and_engagement(postgres_engine, name="A")
    eid_b = _add_engagement(postgres_engine, tid, name="B")
    _seed_node(postgres_engine, tid, eid_a, node_type="risk", title="vendor exit")
    _seed_node(postgres_engine, tid, eid_b, node_type="risk", title="vendor exit risk")
    fake_llm.response = json.dumps([{"title": "Vendor exit pattern", "body": "."}])
    first = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    assert len(first.json()) == 1
    calls_after_first = fake_llm.calls

    second = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    assert len(second.json()) == 1
    assert second.json()[0]["id"] == first.json()[0]["id"]
    assert fake_llm.calls == calls_after_first  # short-circuited


@pytest.mark.asyncio
async def test_dismiss_does_not_resurface_on_refresh(
    t_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid_a = _seed_tenant_and_engagement(postgres_engine, name="A")
    eid_b = _add_engagement(postgres_engine, tid, name="B")
    _seed_node(postgres_engine, tid, eid_a, node_type="risk", title="vendor lock-in")
    _seed_node(postgres_engine, tid, eid_b, node_type="risk", title="vendor lock-in concerns")
    fake_llm.response = json.dumps([{"title": "Vendor lock-in across portfolio", "body": "."}])
    first = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    iid = first.json()[0]["id"]

    dismiss = await t_client.post(f"/internal/v1/tenants/{tid}/insights/{iid}/dismiss", json={"actor_id": "test-user"})
    assert dismiss.status_code == 200
    assert dismiss.json()["status"] == "dismissed"

    second = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    assert second.json() == []  # dismissed row stays dismissed


@pytest.mark.asyncio
async def test_resolve_endpoint(t_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM) -> None:
    tid, eid_a = _seed_tenant_and_engagement(postgres_engine, name="A")
    eid_b = _add_engagement(postgres_engine, tid, name="B")
    _seed_node(postgres_engine, tid, eid_a, node_type="risk", title="staffing crunch")
    _seed_node(postgres_engine, tid, eid_b, node_type="risk", title="staffing crunch concerns")
    fake_llm.response = json.dumps([{"title": "Staffing risk recurring", "body": "."}])
    first = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    iid = first.json()[0]["id"]
    r = await t_client.post(f"/internal/v1/tenants/{tid}/insights/{iid}/resolve", json={"actor_id": "test-user"})
    assert r.status_code == 200
    assert r.json()["status"] == "resolved"
    assert r.json()["decided_by"] == "test-user"


@pytest.mark.asyncio
async def test_auto_resolve_when_predicate_no_longer_fires(
    t_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    tid, eid_a = _seed_tenant_and_engagement(postgres_engine, name="A")
    eid_b = _add_engagement(postgres_engine, tid, name="B")
    nid_a = _seed_node(postgres_engine, tid, eid_a, node_type="risk", title="legacy GIS")
    _seed_node(postgres_engine, tid, eid_b, node_type="risk", title="legacy GIS concerns")
    fake_llm.response = json.dumps([{"title": "Legacy GIS recurring", "body": "."}])
    first = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    iid = first.json()[0]["id"]

    # Drop one of the risk nodes so the predicate no longer fires.
    with postgres_engine.begin() as c:
        c.execute(text("DELETE FROM matrix_nodes WHERE id = :nid"), {"nid": str(nid_a)})

    second = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    assert second.json() == []

    listed = await t_client.get(f"/internal/v1/tenants/{tid}/insights?status=resolved")
    assert len(listed.json()) == 1
    assert listed.json()[0]["id"] == iid
    assert listed.json()[0]["decided_by"] == "auto"


@pytest.mark.asyncio
async def test_list_filters_by_status(t_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM) -> None:
    tid, eid_a = _seed_tenant_and_engagement(postgres_engine, name="A")
    eid_b = _add_engagement(postgres_engine, tid, name="B")
    _seed_node(postgres_engine, tid, eid_a, node_type="risk", title="x risk")
    _seed_node(postgres_engine, tid, eid_b, node_type="risk", title="x risk concerns")
    fake_llm.response = json.dumps([{"title": "X recurring", "body": "."}])
    first = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    assert len(first.json()) == 1
    open_listed = await t_client.get(f"/internal/v1/tenants/{tid}/insights?status=open")
    assert len(open_listed.json()) == 1
    resolved = await t_client.get(f"/internal/v1/tenants/{tid}/insights?status=resolved")
    assert resolved.json() == []


# --- Sprint 1 — per-tenant LLM config endpoints -----------------------------


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'llm-cfg-test')"),
            {"t": str(tid)},
        )
    return tid


@pytest.mark.asyncio
async def test_get_llm_config_returns_null_when_unset(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await t_client.get(f"/internal/v1/tenants/{tid}/llm-config")
    assert r.status_code == 200
    assert r.json() is None


@pytest.mark.asyncio
async def test_put_llm_config_creates_then_get_masks_key(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    body = {"provider": "anthropic", "model_name": "claude-opus-4-5", "api_key": "sk-ant-abcdefghijklmnop"}
    r = await t_client.put(f"/internal/v1/tenants/{tid}/llm-config", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["provider"] == "anthropic"
    assert data["model_name"] == "claude-opus-4-5"
    assert data["has_api_key"] is True
    assert data["api_key_masked"].startswith("sk-a")
    assert data["api_key_masked"].endswith("mnop")
    assert "*" in data["api_key_masked"]
    # GET round-trip never returns the raw key.
    g = await t_client.get(f"/internal/v1/tenants/{tid}/llm-config")
    assert "api_key" not in g.json()


@pytest.mark.asyncio
async def test_put_llm_config_preserves_key_when_omitted(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    await t_client.put(
        f"/internal/v1/tenants/{tid}/llm-config",
        json={"provider": "anthropic", "model_name": "m1", "api_key": "sk-original-key-value"},
    )
    # Update model only — key omitted, must be preserved on the row.
    r = await t_client.put(
        f"/internal/v1/tenants/{tid}/llm-config",
        json={"provider": "anthropic", "model_name": "m2"},
    )
    assert r.status_code == 200
    assert r.json()["model_name"] == "m2"
    assert r.json()["has_api_key"] is True
    # Direct DB check that the original key is still there.
    with postgres_engine.begin() as c:
        row = c.execute(
            text("SELECT api_key FROM tenant_llm_configs WHERE tenant_id = :t"),
            {"t": str(tid)},
        ).scalar_one()
    assert row == "sk-original-key-value"


@pytest.mark.asyncio
async def test_put_llm_config_rejects_unknown_provider(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await t_client.put(
        f"/internal/v1/tenants/{tid}/llm-config",
        json={"provider": "made-up", "model_name": "x"},
    )
    assert r.status_code == 422
    assert "invalid provider" in r.text


@pytest.mark.asyncio
async def test_put_llm_config_404_when_tenant_missing(t_client: AsyncClient) -> None:
    r = await t_client.put(
        f"/internal/v1/tenants/{uuid.uuid4()}/llm-config",
        json={"provider": "stub"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_stub_provider_in_db_short_circuits_env_fallback(
    t_client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    """Tenant config provider=stub overrides the env-fallback fake_llm.

    The Master Strategist refresh route resolves the provider per-request:
    when a tenant row exists we use it instead of the Depends fallback.
    Setting provider=stub means the real stub provider runs (not fake_llm),
    so fake_llm.calls stays at zero even though a candidate fires.
    """
    tid, eid_a = _seed_tenant_and_engagement(postgres_engine, name="A")
    eid_b = _add_engagement(postgres_engine, tid, name="B")
    _seed_node(postgres_engine, tid, eid_a, node_type="risk", title="db override risk")
    _seed_node(postgres_engine, tid, eid_b, node_type="risk", title="db override risk pattern")
    # Persist the stub override AFTER seeding so the route's resolver picks it up.
    await t_client.put(
        f"/internal/v1/tenants/{tid}/llm-config",
        json={"provider": "stub"},
    )
    # Refresh runs the real stub (deterministic [] response from create_stub_provider),
    # not fake_llm. We accept any 200; key assertion is fake_llm was NOT called.
    r = await t_client.post(f"/internal/v1/tenants/{tid}/insights/refresh")
    assert r.status_code == 200
    assert fake_llm.calls == 0
