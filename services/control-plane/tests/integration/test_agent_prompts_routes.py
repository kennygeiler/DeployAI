"""Sprint 5 — per-tenant agent prompt overrides (integration)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.master_strategist import default_system_prompt as master_strategist_default_prompt
from control_plane.agents.matrix_extractor import default_system_prompt as matrix_extractor_default_prompt
from control_plane.agents.oracle import default_system_prompt as oracle_default_prompt
from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def t_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "ap-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "ap-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'agent-prompts-test')"),
            {"t": str(tid)},
        )
    return tid


@pytest.mark.asyncio
async def test_list_returns_all_defaults_when_no_overrides(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await t_client.get(f"/internal/v1/tenants/{tid}/agent-prompts")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body["prompts"].keys()) == {"cartographer", "oracle", "master_strategist"}
    assert body["prompts"]["cartographer"]["is_default"] is True
    assert body["prompts"]["cartographer"]["value"] == matrix_extractor_default_prompt()
    assert body["prompts"]["oracle"]["is_default"] is True
    assert body["prompts"]["oracle"]["value"] == oracle_default_prompt()
    assert body["prompts"]["master_strategist"]["is_default"] is True
    assert body["prompts"]["master_strategist"]["value"] == master_strategist_default_prompt()


@pytest.mark.asyncio
async def test_put_then_list_returns_override(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    put = await t_client.put(
        f"/internal/v1/tenants/{tid}/agent-prompts/oracle",
        json={"prompt_text": "you are a custom oracle"},
    )
    assert put.status_code == 200, put.text
    assert put.json() == {"value": "you are a custom oracle", "is_default": False}

    listed = await t_client.get(f"/internal/v1/tenants/{tid}/agent-prompts")
    assert listed.status_code == 200
    prompts = listed.json()["prompts"]
    assert prompts["oracle"]["value"] == "you are a custom oracle"
    assert prompts["oracle"]["is_default"] is False
    # Untouched agents stay on the defaults.
    assert prompts["cartographer"]["is_default"] is True
    assert prompts["master_strategist"]["is_default"] is True


@pytest.mark.asyncio
async def test_put_upserts_existing_row(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    await t_client.put(
        f"/internal/v1/tenants/{tid}/agent-prompts/cartographer",
        json={"prompt_text": "v1"},
    )
    r = await t_client.put(
        f"/internal/v1/tenants/{tid}/agent-prompts/cartographer",
        json={"prompt_text": "v2"},
    )
    assert r.status_code == 200
    assert r.json()["value"] == "v2"
    # Only one row should exist for that (tenant, agent_name).
    with postgres_engine.begin() as c:
        n = c.execute(
            text("SELECT count(*) FROM tenant_agent_prompts WHERE tenant_id = :t AND agent_name = 'cartographer'"),
            {"t": str(tid)},
        ).scalar_one()
    assert n == 1


@pytest.mark.asyncio
async def test_delete_resets_to_default(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    await t_client.put(
        f"/internal/v1/tenants/{tid}/agent-prompts/master_strategist",
        json={"prompt_text": "override"},
    )
    d = await t_client.delete(f"/internal/v1/tenants/{tid}/agent-prompts/master_strategist")
    assert d.status_code == 204

    listed = await t_client.get(f"/internal/v1/tenants/{tid}/agent-prompts")
    prompts = listed.json()["prompts"]
    assert prompts["master_strategist"]["is_default"] is True
    assert prompts["master_strategist"]["value"] == master_strategist_default_prompt()


@pytest.mark.asyncio
async def test_delete_when_no_override_is_a_noop(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await t_client.delete(f"/internal/v1/tenants/{tid}/agent-prompts/oracle")
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_put_rejects_unknown_agent_name(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await t_client.put(
        f"/internal/v1/tenants/{tid}/agent-prompts/nonsense",
        json={"prompt_text": "x"},
    )
    assert r.status_code == 422
    assert "invalid agent_name" in r.text


@pytest.mark.asyncio
async def test_delete_rejects_unknown_agent_name(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await t_client.delete(f"/internal/v1/tenants/{tid}/agent-prompts/nonsense")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_404_when_tenant_missing(t_client: AsyncClient) -> None:
    r = await t_client.get(f"/internal/v1/tenants/{uuid.uuid4()}/agent-prompts")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_404_when_tenant_missing(t_client: AsyncClient) -> None:
    r = await t_client.put(
        f"/internal/v1/tenants/{uuid.uuid4()}/agent-prompts/oracle",
        json={"prompt_text": "x"},
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_put_rejects_empty_prompt(t_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = _seed_tenant(postgres_engine)
    r = await t_client.put(
        f"/internal/v1/tenants/{tid}/agent-prompts/oracle",
        json={"prompt_text": ""},
    )
    assert r.status_code == 422
