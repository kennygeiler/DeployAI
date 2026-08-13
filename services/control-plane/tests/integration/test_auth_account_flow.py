"""Self-serve accounts, full stack: signup → login → password change → invite →
accept, plus the signup gate, login rate limit, and user_invites RLS.

Runs against real Postgres (testcontainer, migrated) + real Redis, exactly like
test_account_provision_flow.py.
"""

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
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import create_async_engine

from control_plane.auth.jwt_tokens import clear_jwt_key_cache
from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.domain.app_identity.models import UserInvite
from control_plane.infra.redis_client import clear_redis_client, close_async_redis
from control_plane.main import app

from .test_account_provision_flow import _async_database_url_from_engine

_APP_PASSWORD = "deployai-app-rls-25"
GOOD_PASSWORD = "original passphrase 1"
NEW_PASSWORD = "rotated passphrase 2"


def _docker_available() -> bool:
    try:
        import docker

        docker.from_env().ping()
        return True
    except Exception:
        return False


def _write_rsa(tmp: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = tmp / "a-priv.pem"
    pub = tmp / "a-pub.pem"
    priv.write_bytes(
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    pub.write_bytes(
        key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )
    return priv, pub


def _async_url_for(sync_url: str, *, user: str, password: str) -> str:
    remainder = sync_url.split("@", 1)[1]
    return f"postgresql+psycopg://{user}:{password}@{remainder}"


@pytest.fixture(scope="module", autouse=True)
def _enable_deployai_app_login(postgres_engine: Engine) -> Generator[None]:
    with postgres_engine.begin() as conn:
        conn.execute(text(f"ALTER ROLE deployai_app WITH LOGIN PASSWORD '{_APP_PASSWORD}'"))
    yield


@pytest.fixture(scope="module")
def redis_url_module() -> Generator[str]:
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
async def auth_client(
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
    monkeypatch.setenv("DEPLOYAI_SELF_SERVE_SIGNUP", "1")
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "int-auth-test")
    clear_settings_cache()
    clear_jwt_key_cache()
    clear_redis_client()
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client
    finally:
        await close_async_redis()
        clear_redis_client()
        clear_jwt_key_cache()
        clear_settings_cache()
        clear_engine_cache()


def _fwd(ip: str) -> dict[str, str]:
    """Distinct client IPs per test so the per-IP attempt window (Redis-backed,
    module-lived container) never bleeds between tests."""
    return {"x-forwarded-for": ip}


async def _signup(
    client: AsyncClient,
    *,
    email: str,
    workspace: str,
    ip: str,
    password: str = GOOD_PASSWORD,
) -> dict[str, object]:
    r = await client.post(
        "/api/v1/auth/signup",
        headers=_fwd(ip),
        json={
            "email": email,
            "password": password,
            "workspace_name": workspace,
            "display_name": "Founder",
        },
    )
    assert r.status_code == 201, r.text
    return cast(dict[str, object], r.json())


@pytest.mark.integration
async def test_full_signup_login_password_change_invite_accept_flow(
    auth_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    body = await _signup(auth_client, email="founder@acme.example", workspace="Acme", ip="203.0.113.10")
    tid = uuid.UUID(str(body["tenant_id"]))
    uid = uuid.UUID(str(body["user_id"]))
    assert body["roles"] == ["customer_admin"]

    # DB state: tenant + DEK-wrapped, creator is customer_admin with an argon2id
    # hash; the hash never appears in the response body.
    with postgres_engine.connect() as conn:
        trow = conn.execute(
            text("SELECT name, tenant_dek_ciphertext FROM app_tenants WHERE id = :id"), {"id": tid}
        ).one()
        assert trow[0] == "Acme"
        assert trow[1] is not None
        urow = conn.execute(
            text("SELECT roles::text, password_hash, given_name FROM app_users WHERE id = :id"),
            {"id": uid},
        ).one()
        assert "customer_admin" in urow[0]
        assert str(urow[1]).startswith("$argon2id$")
        assert urow[2] == "Founder"
        assert str(urow[1]) not in str(body)
        kinds = [
            r[0]
            for r in conn.execute(text("SELECT source_kind FROM ledger_events WHERE tenant_id = :tid"), {"tid": tid})
        ]
        assert "account_signup" in kinds

    # Login (same session machinery as OIDC: dep_access/dep_refresh cookies).
    r = await auth_client.post(
        "/api/v1/auth/login",
        headers=_fwd("203.0.113.10"),
        json={"email": "Founder@Acme.example", "password": GOOD_PASSWORD},
    )
    assert r.status_code == 200, r.text
    login = r.json()
    assert login["tenant_id"] == str(tid)
    assert any(c.startswith("dep_access=") for c in r.headers.get_list("set-cookie"))
    access = login["access_token"]
    old_refresh = login["refresh_token"]

    # /me works with the bearer token.
    me = await auth_client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200, me.text
    assert me.json()["email"] == "founder@acme.example"
    assert me.json()["tenant_name"] == "Acme"
    assert me.json()["has_password"] is True

    # Password change revokes the old refresh session…
    r = await auth_client.post(
        "/api/v1/auth/password",
        headers={"Authorization": f"Bearer {access}", **_fwd("203.0.113.10")},
        json={"current_password": GOOD_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert r.status_code == 200, r.text
    refreshed = await auth_client.post("/auth/refresh", json={"tenant_id": str(tid), "refresh_token": old_refresh})
    assert refreshed.status_code == 401
    # …old password dead, new password lives.
    assert (
        await auth_client.post(
            "/api/v1/auth/login",
            headers=_fwd("203.0.113.11"),
            json={"email": "founder@acme.example", "password": GOOD_PASSWORD},
        )
    ).status_code == 401
    r = await auth_client.post(
        "/api/v1/auth/login",
        headers=_fwd("203.0.113.11"),
        json={"email": "founder@acme.example", "password": NEW_PASSWORD},
    )
    assert r.status_code == 200
    admin_access = r.json()["access_token"]

    # Invite: create (admin) → preview (public) → accept (public, mints session).
    r = await auth_client.post(
        "/api/v1/auth/invites",
        headers={"Authorization": f"Bearer {admin_access}"},
        json={"email": "teammate@acme.example", "role": "deployment_strategist"},
    )
    assert r.status_code == 201, r.text
    token = str(r.json()["join_path"]).removeprefix("/join/")

    listed = await auth_client.get("/api/v1/auth/invites", headers={"Authorization": f"Bearer {admin_access}"})
    assert listed.status_code == 200
    assert [i["email"] for i in listed.json()] == ["teammate@acme.example"]

    preview = await auth_client.get(
        "/api/v1/auth/invites/preview", params={"token": token}, headers=_fwd("203.0.113.12")
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["workspace_name"] == "Acme"

    r = await auth_client.post(
        "/api/v1/auth/invites/accept",
        headers=_fwd("203.0.113.12"),
        json={"token": token, "password": "teammate passphrase 9", "display_name": "Teammate"},
    )
    assert r.status_code == 201, r.text
    accepted = r.json()
    assert accepted["tenant_id"] == str(tid)
    assert accepted["roles"] == ["deployment_strategist"]

    # Single-use: the same token is dead now.
    assert (
        await auth_client.post(
            "/api/v1/auth/invites/accept",
            headers=_fwd("203.0.113.12"),
            json={"token": token, "password": "teammate passphrase 9", "display_name": "Replay"},
        )
    ).status_code == 404

    # Invited user can log in.
    r = await auth_client.post(
        "/api/v1/auth/login",
        headers=_fwd("203.0.113.13"),
        json={"email": "teammate@acme.example", "password": "teammate passphrase 9"},
    )
    assert r.status_code == 200
    assert r.json()["roles"] == ["deployment_strategist"]


@pytest.mark.integration
async def test_signup_disabled_is_404(auth_client: AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_SELF_SERVE_SIGNUP", "0")
    clear_settings_cache()
    r = await auth_client.post(
        "/api/v1/auth/signup",
        headers=_fwd("203.0.113.20"),
        json={
            "email": "x@y.example",
            "password": GOOD_PASSWORD,
            "workspace_name": "Nope",
            "display_name": "N",
        },
    )
    assert r.status_code == 404


@pytest.mark.integration
async def test_login_rate_limit_trips_in_redis(auth_client: AsyncClient) -> None:
    ip = "203.0.113.30"
    for _ in range(10):
        r = await auth_client.post(
            "/api/v1/auth/login",
            headers=_fwd(ip),
            json={"email": "ratelimit@x.example", "password": "wrong password 1"},
        )
        assert r.status_code == 401
    r = await auth_client.post(
        "/api/v1/auth/login",
        headers=_fwd(ip),
        json={"email": "ratelimit@x.example", "password": "wrong password 1"},
    )
    assert r.status_code == 429
    assert r.json()["detail"] == "too many attempts; try again later"


@pytest.mark.integration
async def test_user_invites_rls_blocks_cross_tenant_reads(
    auth_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    a = await _signup(auth_client, email="a@rls-a.example", workspace="RLS A", ip="203.0.113.40")
    b = await _signup(auth_client, email="b@rls-b.example", workspace="RLS B", ip="203.0.113.41")
    tid_a = uuid.UUID(str(a["tenant_id"]))
    tid_b = uuid.UUID(str(b["tenant_id"]))

    r = await auth_client.post(
        "/api/v1/auth/invites",
        headers={"Authorization": f"Bearer {a['access_token']}"},
        json={"email": "peek@rls-a.example", "role": "fde"},
    )
    assert r.status_code == 201, r.text

    raw_sync = cast(str, postgres_engine.url.render_as_string(hide_password=False))
    rls_engine = create_async_engine(
        _async_url_for(raw_sync, user="deployai_app", password=_APP_PASSWORD),
        pool_pre_ping=True,
    )
    try:
        async with TenantScopedSession(tid_b, rls_engine) as ts:
            visible = (await ts.execute(select(UserInvite.id))).all()
        assert visible == []
        async with TenantScopedSession(tid_a, rls_engine) as ts:
            own = (await ts.execute(select(UserInvite.id))).all()
        assert len(own) == 1
    finally:
        await rls_engine.dispose()
