"""Engagement member auto-provision by email (G2.a)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from control_plane.db import clear_engine_cache
from control_plane.domain.app_identity.models import AppUser
from control_plane.domain.ledger import LedgerEvent
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'member-provision') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_user(engine: Engine, user_id: uuid.UUID, tenant_id: uuid.UUID, *, email: str, user_name: str) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_users (id, tenant_id, user_name, email) VALUES (:u, :t, :name, :email)"),
            {"u": str(user_id), "t": str(tenant_id), "name": user_name, "email": email},
        )


@pytest_asyncio.fixture
async def e_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "mp-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "mp-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest_asyncio.fixture
async def session_factory(
    postgres_engine: Engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    eng: AsyncEngine = create_async_engine(_async_url(postgres_engine), future=True)
    try:
        yield async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    finally:
        await eng.dispose()


async def _new_engagement(e_client: AsyncClient, postgres_engine: Engine) -> tuple[uuid.UUID, str]:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    r = await e_client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "GA member provision"})
    assert r.status_code == 201, r.text
    return tid, r.json()["id"]


async def _ledger_kinds(factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID) -> list[str]:
    async with factory() as session:
        rows = (
            await session.execute(
                select(LedgerEvent.source_kind)
                .where(LedgerEvent.tenant_id == tenant_id)
                .order_by(LedgerEvent.occurred_at)
            )
        ).all()
    return [r[0] for r in rows]


async def _count_users(factory: async_sessionmaker[AsyncSession], tenant_id: uuid.UUID) -> int:
    async with factory() as session:
        n = (await session.execute(select(func.count(AppUser.id)).where(AppUser.tenant_id == tenant_id))).scalar_one()
    return int(n)


@pytest.mark.asyncio
async def test_email_existing_user_reuses(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    uid = uuid.uuid4()
    _ins_user(postgres_engine, uid, tid, email="existing@x.com", user_name="existing@x.com")

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"email": "existing@x.com", "role": "fde"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == str(uid)

    assert await _count_users(session_factory, tid) == 1
    kinds = await _ledger_kinds(session_factory, tid)
    assert "user_provisioned" not in kinds
    assert "member_added" in kinds


@pytest.mark.asyncio
async def test_email_new_user_provisions(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"email": "new@x.com", "role": "fde"},
    )
    assert r.status_code == 201, r.text
    new_uid = r.json()["user_id"]

    async with session_factory() as session:
        user = await session.get(AppUser, uuid.UUID(new_uid))
        assert user is not None
        assert user.tenant_id == tid
        assert user.email == "new@x.com"
        assert user.user_name == "new@x.com"

    kinds = await _ledger_kinds(session_factory, tid)
    assert kinds.count("user_provisioned") == 1
    assert kinds.count("member_added") == 1
    assert kinds.index("user_provisioned") < kinds.index("member_added")


@pytest.mark.asyncio
async def test_email_case_insensitive_match(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    uid = uuid.uuid4()
    _ins_user(postgres_engine, uid, tid, email="existing@x.com", user_name="existing@x.com")

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"email": "EXISTING@x.com", "role": "fde"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["user_id"] == str(uid)
    assert await _count_users(session_factory, tid) == 1


@pytest.mark.asyncio
async def test_user_id_path_unchanged(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    uid = uuid.uuid4()
    _ins_user(postgres_engine, uid, tid, email="byid@x.com", user_name="byid@x.com")

    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uid), "role": "fde"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user_id"] == str(uid)
    assert body["role"] == "fde"

    assert await _count_users(session_factory, tid) == 1
    kinds = await _ledger_kinds(session_factory, tid)
    assert "user_provisioned" not in kinds


@pytest.mark.asyncio
async def test_both_user_id_and_email_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"user_id": str(uuid.uuid4()), "email": "x@x.com", "role": "fde"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_neither_user_id_nor_email_422(e_client: AsyncClient, postgres_engine: Engine) -> None:
    tid, eid = await _new_engagement(e_client, postgres_engine)
    r = await e_client.post(
        f"/internal/v1/engagements/{eid}/members?tenant_id={tid}",
        json={"role": "fde"},
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_cross_tenant_isolation_provisions_new_user(
    e_client: AsyncClient,
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a)
    _ins_tenant(postgres_engine, tid_b)
    # Tenant B has a user with this email; tenant A should not see them.
    uid_b = uuid.uuid4()
    _ins_user(postgres_engine, uid_b, tid_b, email="shared@x.com", user_name="shared@x.com")

    r_eng = await e_client.post(f"/internal/v1/engagements?tenant_id={tid_a}", json={"name": "tenant A engagement"})
    assert r_eng.status_code == 201
    eid_a = r_eng.json()["id"]

    r = await e_client.post(
        f"/internal/v1/engagements/{eid_a}/members?tenant_id={tid_a}",
        json={"email": "shared@x.com", "role": "fde"},
    )
    assert r.status_code == 201, r.text
    new_uid = uuid.UUID(r.json()["user_id"])
    assert new_uid != uid_b

    async with session_factory() as session:
        a_users = (await session.execute(select(AppUser).where(AppUser.tenant_id == tid_a))).scalars().all()
        b_users = (await session.execute(select(AppUser).where(AppUser.tenant_id == tid_b))).scalars().all()
    assert len(a_users) == 1
    assert a_users[0].id == new_uid
    assert len(b_users) == 1
    assert b_users[0].id == uid_b
