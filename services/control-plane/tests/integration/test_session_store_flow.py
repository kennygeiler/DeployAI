"""Story 2-4: mint → refresh → logout; revoke-all; cross-tenant refresh denied."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from testcontainers.redis import RedisContainer

from control_plane.auth.jwt_tokens import clear_jwt_key_cache
from control_plane.config.settings import clear_settings_cache
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


@pytest.fixture(scope="module")
def redis_url_module() -> str:
    if not _docker_available():
        pytest.skip("Docker not available")
    c = RedisContainer("redis:7-alpine")
    c.start()
    try:
        host = c.get_container_host_ip()
        port = c.get_exposed_port(6379)
        yield f"redis://{host}:{port}/0"
    finally:
        c.stop()


@pytest_asyncio.fixture
async def session_client(
    redis_url_module: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DEPLOYAI_REDIS_URL", redis_url_module)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    monkeypatch.setenv("DEPLOYAI_ALLOW_TEST_SESSION_MINT", "1")
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "int-session-test")
    clear_settings_cache()
    clear_jwt_key_cache()
    clear_redis_client()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            client.headers["X-DeployAI-Internal-Key"] = "int-session-test"
            yield client
    finally:
        await close_async_redis()
        clear_redis_client()
        clear_jwt_key_cache()
        clear_settings_cache()


@pytest.mark.integration
async def test_mint_refresh_logout_happy(
    session_client: AsyncClient,
) -> None:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    m = await session_client.post(
        "/internal/v1/test/session-tokens",
        json={
            "tenant_id": str(tid),
            "user_id": str(uid),
            "roles": ["deployment_strategist", "platform_admin"],
        },
    )
    assert m.status_code == 201, m.text
    mint = m.json()
    rft = mint["refresh_token"]
    r1 = await session_client.post(
        "/auth/refresh",
        json={"tenant_id": str(tid), "refresh_token": rft},
    )
    assert r1.status_code == 200, r1.text
    r1b = r1.json()
    new_rt = r1b["refresh_token"]
    out = await session_client.post(
        "/auth/logout",
        json={"tenant_id": str(tid), "refresh_token": new_rt},
    )
    assert out.status_code == 204, out.text
    bad = await session_client.post(
        "/auth/refresh",
        json={"tenant_id": str(tid), "refresh_token": new_rt},
    )
    assert bad.status_code == 401


@pytest.mark.integration
async def test_reject_refresh_wrong_tenant(
    session_client: AsyncClient,
) -> None:
    tid = uuid.uuid4()
    other = uuid.uuid4()
    uid = uuid.uuid4()
    m = await session_client.post(
        "/internal/v1/test/session-tokens",
        json={
            "tenant_id": str(tid),
            "user_id": str(uid),
            "roles": ["platform_admin"],
        },
    )
    rft = m.json()["refresh_token"]
    r = await session_client.post(
        "/auth/refresh",
        json={"tenant_id": str(other), "refresh_token": rft},
    )
    assert r.status_code == 403


@pytest.mark.integration
async def test_revoke_all(
    session_client: AsyncClient,
) -> None:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    m = await session_client.post(
        "/internal/v1/test/session-tokens",
        json={"tenant_id": str(tid), "user_id": str(uid), "roles": ["platform_admin"]},
    )
    at = m.json()["access_token"]
    r = await session_client.post(
        f"/auth/sessions/revoke-all/{uid}",
        headers={"Authorization": f"Bearer {at}"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["deleted_refresh_keys"] == 1
