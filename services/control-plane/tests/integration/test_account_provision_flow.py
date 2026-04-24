"""Story 2-5: POST /platform/accounts (platform_admin); canonical baseline empty; RLS."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Generator
from pathlib import Path
from typing import cast

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from deployai_tenancy import TenantScopedSession
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine

from control_plane.auth.jwt_tokens import clear_jwt_key_cache
from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.infra.redis_client import clear_redis_client, close_async_redis
from control_plane.main import app


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


def _write_rsa(tmp: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_b = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_b = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv = tmp / "s-priv.pem"
    pub = tmp / "s-pub.pem"
    priv.write_bytes(priv_b)
    pub.write_bytes(pub_b)
    return priv, pub


def _async_database_url_from_engine(postgres_engine: Engine) -> str:
    u = postgres_engine.url.set(drivername="postgresql+psycopg")
    return u.render_as_string(hide_password=False)


_APP_PASSWORD = "deployai-app-rls-25"


def _async_url_for(sync_url: str, *, user: str, password: str) -> str:
    remainder = sync_url.split("@", 1)[1]
    return f"postgresql+psycopg://{user}:{password}@{remainder}"


@pytest.fixture(scope="module", autouse=True)
def _enable_deployai_app_login(postgres_engine: Engine) -> Generator[None]:
    """RLS is bypassed for superusers; integration tests that assert RLS use ``deployai_app`` (Story 1.9)."""
    with postgres_engine.begin() as conn:
        conn.execute(text(f"ALTER ROLE deployai_app WITH LOGIN PASSWORD '{_APP_PASSWORD}'"))
    yield


@pytest.fixture(scope="module")
def redis_url_module() -> str:
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


@pytest_asyncio.fixture
async def platform_client(
    postgres_engine: Engine,
    redis_url_module: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_REDIS_URL", redis_url_module)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    monkeypatch.setenv("DEPLOYAI_ALLOW_TEST_SESSION_MINT", "1")
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "int-platform-test")
    clear_settings_cache()
    clear_jwt_key_cache()
    clear_redis_client()
    clear_engine_cache()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            client.headers["X-DeployAI-Internal-Key"] = "int-platform-test"
            yield client
    finally:
        await close_async_redis()
        clear_redis_client()
        clear_jwt_key_cache()
        clear_settings_cache()
        clear_engine_cache()


async def _mint_access(client: AsyncClient, *, roles: list[str]) -> str:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    m = await client.post(
        "/internal/v1/test/session-tokens",
        json={
            "tenant_id": str(tid),
            "user_id": str(uid),
            "roles": roles,
        },
    )
    assert m.status_code == 201, m.text
    return m.json()["access_token"]  # type: ignore[no-any-return]


@pytest.mark.integration
async def test_post_platform_account_creates_tenant_user_and_dek(
    platform_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    token = await _mint_access(platform_client, roles=["platform_admin"])
    r = await platform_client.post(
        "/platform/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "organization_name": "Acme Corp",
            "initial_strategist_email": "strategist@acme.example",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    tid = uuid.UUID(body["tenant_id"])
    user_id = uuid.UUID(body["initial_strategist_user_id"])
    assert body["created_at"]

    with postgres_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT name, scim_bearer_token_hash, tenant_dek_ciphertext, tenant_dek_key_id "
                "FROM app_tenants WHERE id = :id"
            ),
            {"id": tid},
        ).one()
        assert row[0] == "Acme Corp"
        assert row[1] is None
        assert row[2] is not None and len(str(row[2])) > 0
        assert row[3] == "stub-local"
        urow = conn.execute(
            text("SELECT email, roles::text FROM app_users WHERE id = :id AND tenant_id = :tid"),
            {"id": user_id, "tid": tid},
        ).one()
        assert urow[0] == "strategist@acme.example"
        assert "deployment_strategist" in urow[1]

    raw_sync = cast(str, postgres_engine.url.render_as_string(hide_password=False))
    rls_engine = create_async_engine(
        _async_url_for(raw_sync, user="deployai_app", password=_APP_PASSWORD),
        pool_pre_ping=True,
    )
    try:
        async with TenantScopedSession(tid, rls_engine) as ts:
            n = (await ts.execute(select(func.count()).select_from(CanonicalMemoryEvent))).scalar_one()
        assert int(n) == 0
    finally:
        await rls_engine.dispose()


@pytest.mark.integration
async def test_post_platform_account_requires_platform_admin(
    platform_client: AsyncClient,
) -> None:
    token = await _mint_access(platform_client, roles=["deployment_strategist"])
    r = await platform_client.post(
        "/platform/accounts",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "organization_name": "X",
            "initial_strategist_email": "a@b.example",
        },
    )
    assert r.status_code == 403, r.text


@pytest.mark.integration
async def test_post_platform_account_cross_tenant_canonical_isolation(
    platform_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    t_admin = await _mint_access(platform_client, roles=["platform_admin"])
    r1 = await platform_client.post(
        "/platform/accounts",
        headers={"Authorization": f"Bearer {t_admin}"},
        json={"organization_name": "Tenant A", "initial_strategist_email": "a@tenant-a.example"},
    )
    r2 = await platform_client.post(
        "/platform/accounts",
        headers={"Authorization": f"Bearer {t_admin}"},
        json={"organization_name": "Tenant B", "initial_strategist_email": "b@tenant-b.example"},
    )
    assert r1.status_code == 201 and r2.status_code == 201, (r1.text, r2.text)
    t_a = uuid.UUID(r1.json()["tenant_id"])
    t_b = uuid.UUID(r2.json()["tenant_id"])
    eid = uuid.uuid4()
    with postgres_engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO canonical_memory_events
                    (id, tenant_id, event_type, occurred_at, evidence_span, payload)
                VALUES
                    (:id, :tid, 'integration.marker', now(), '{}'::jsonb, '{}'::jsonb)
                """
            ),
            {"id": eid, "tid": t_a},
        )

    raw_sync = cast(str, postgres_engine.url.render_as_string(hide_password=False))
    rls_engine = create_async_engine(
        _async_url_for(raw_sync, user="deployai_app", password=_APP_PASSWORD),
        pool_pre_ping=True,
    )
    try:
        async with TenantScopedSession(t_b, rls_engine) as ts:
            n_b = (
                await ts.execute(select(CanonicalMemoryEvent.id).where(CanonicalMemoryEvent.id == eid))
            ).one_or_none()
        assert n_b is None
    finally:
        await rls_engine.dispose()
