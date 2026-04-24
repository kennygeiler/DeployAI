"""Epic 2 stories 2-6/2-7: integration disable + break-glass session plumbing."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.auth.jwt_tokens import clear_jwt_key_cache
from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.infra.redis_client import clear_redis_client, close_async_redis
from control_plane.main import app

from .test_account_provision_flow import (
    _async_database_url_from_engine,
    _docker_available,
    _write_rsa,
)


@pytest.fixture(scope="module")
def redis_url_module_epic2() -> str:
    if not _docker_available():
        pytest.skip("Docker not available")
    from testcontainers.redis import RedisContainer

    c = RedisContainer("redis:7-alpine")
    c.start()
    try:
        host = c.get_container_host_ip()
        port = c.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        c.stop()


pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def epic2_client(
    postgres_engine: Engine,
    redis_url_module_epic2: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_REDIS_URL", redis_url_module_epic2)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    monkeypatch.setenv("DEPLOYAI_ALLOW_TEST_SESSION_MINT", "1")
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "int-epic2")
    monkeypatch.setenv("DEPLOYAI_BREAK_GLASS_BYPASS_WEBAUTHN", "1")
    clear_settings_cache()
    clear_jwt_key_cache()
    clear_redis_client()
    clear_engine_cache()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            client.headers["X-DeployAI-Internal-Key"] = "int-epic2"
            yield client
    finally:
        await close_async_redis()
        clear_redis_client()
        clear_jwt_key_cache()
        clear_settings_cache()
        clear_engine_cache()


def _ins_tenant_and_integration(conn: Engine, *, tid: uuid.UUID, iid: uuid.UUID) -> None:
    with conn.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'Epic2 Tenant')"),
            {"t": tid},
        )
        c.execute(
            text(
                "INSERT INTO integrations (id, tenant_id, provider, display_name) "
                "VALUES (:i, :t, 'm365_calendar', 'Test Calendar')"
            ),
            {"i": iid, "t": tid},
        )


async def _mint(client: AsyncClient, *, tid: uuid.UUID, uid: uuid.UUID, roles: list[str]) -> str:
    m = await client.post(
        "/internal/v1/test/session-tokens",
        json={"tenant_id": str(tid), "user_id": str(uid), "roles": roles},
    )
    assert m.status_code == 201, m.text
    return m.json()["access_token"]  # type: ignore[no-any-return]


@pytest.mark.asyncio
async def test_tenant_scoped_strategist_may_call_kill_switch(
    epic2_client: AsyncClient, postgres_engine: Engine
) -> None:
    tid = uuid.uuid4()
    iid = uuid.uuid4()
    _ins_tenant_and_integration(postgres_engine, tid=tid, iid=iid)
    su = uuid.uuid4()
    token = await _mint(
        epic2_client,
        tid=tid,
        uid=su,
        roles=["deployment_strategist"],
    )
    r = await epic2_client.post(
        f"/integrations/{iid}/disable",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    b = r.json()
    assert b.get("ok") is True
    with postgres_engine.connect() as c:
        row = c.execute(
            text("SELECT state, disabled_at IS NOT NULL FROM integrations WHERE id = :i"),
            {"i": iid},
        ).one()
        assert row[0] == "disabled" and row[1] is True


@pytest.mark.asyncio
async def test_break_glass_dual_approval_and_approve_with_same_sub_fails(
    epic2_client: AsyncClient, postgres_engine: Engine
) -> None:
    tid = uuid.uuid4()
    with postgres_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'BG Tenant')"),
            {"t": tid},
        )
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    t1 = await _mint(epic2_client, tid=tid, uid=u1, roles=["platform_admin"])
    t2 = await _mint(epic2_client, tid=tid, uid=u2, roles=["platform_admin"])
    rq = await epic2_client.post(
        "/break-glass/request",
        headers={"Authorization": f"Bearer {t1}"},
        json={"tenant_id": str(tid), "requested_scope": "tenant_data_read"},
    )
    assert rq.status_code == 201, rq.text
    sid = uuid.UUID(rq.json()["id"])
    bad = await epic2_client.post(
        f"/break-glass/approve/{sid}",
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert bad.status_code == 400
    good = await epic2_client.post(
        f"/break-glass/approve/{sid}",
        headers={"Authorization": f"Bearer {t2}"},
    )
    assert good.status_code == 200, good.text
    assert good.json()["status"] == "active"
    assert good.json()["approver_sub"] == str(u2)
    d = await epic2_client.delete(
        f"/break-glass/{sid}",
        headers={"Authorization": f"Bearer {t1}"},
    )
    assert d.status_code == 204


@pytest.mark.asyncio
async def test_webauthn_header_required_without_bypass(
    epic2_client: AsyncClient, postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = uuid.uuid4()
    with postgres_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'W Tenant')"),
            {"t": tid},
        )
    u = uuid.uuid4()
    tok = await _mint(epic2_client, tid=tid, uid=u, roles=["platform_admin"])
    monkeypatch.setenv("DEPLOYAI_BREAK_GLASS_BYPASS_WEBAUTHN", "0")
    clear_settings_cache()
    try:
        r = await epic2_client.post(
            "/break-glass/request",
            headers={"Authorization": f"Bearer {tok}"},
            json={"tenant_id": str(tid), "requested_scope": "x"},
        )
        assert r.status_code == 403, r.text
    finally:
        monkeypatch.setenv("DEPLOYAI_BREAK_GLASS_BYPASS_WEBAUTHN", "1")
        clear_settings_cache()
