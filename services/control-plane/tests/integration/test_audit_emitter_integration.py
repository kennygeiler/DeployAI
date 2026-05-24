"""End-to-end: emit_audit_event writes a row that reads back per-tenant."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from control_plane.audit import emit_audit_event
from control_plane.domain.strategist_personal import StrategistActivityEvent

pytestmark = pytest.mark.integration


def _async_url(eng: Engine) -> str:
    return eng.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def session_factory(
    postgres_engine: Engine,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    eng: AsyncEngine = create_async_engine(_async_url(postgres_engine), future=True)
    try:
        yield async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    finally:
        await eng.dispose()


def _seed_tenant(eng: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'audit-emit')"),
            {"t": str(tid)},
        )
    return tid


@pytest.mark.asyncio
async def test_emit_then_readback(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    aid = uuid.uuid4()
    ref = uuid.uuid4()

    async with session_factory() as session:
        row = await emit_audit_event(
            session,
            tenant_id=tid,
            actor_id=aid,
            category="break_glass.requested",
            summary="bg requested via test",
            detail={"session_id": str(uuid.uuid4()), "initiator_sub": "tester"},
            ref_id=ref,
        )
        new_id = row.id
        await session.commit()

    async with session_factory() as session:
        out = (
            (await session.execute(select(StrategistActivityEvent).where(StrategistActivityEvent.tenant_id == tid)))
            .scalars()
            .all()
        )
    assert len(out) == 1
    persisted = out[0]
    assert persisted.id == new_id
    assert persisted.actor_id == aid
    assert persisted.category == "break_glass.requested"
    assert persisted.summary == "bg requested via test"
    assert persisted.detail["initiator_sub"] == "tester"
    assert persisted.ref_id == ref
    assert persisted.created_at is not None


@pytest.mark.asyncio
async def test_tenant_isolation_on_readback(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid_a = _seed_tenant(postgres_engine)
    tid_b = _seed_tenant(postgres_engine)
    actor = uuid.uuid4()

    async with session_factory() as session:
        await emit_audit_event(
            session,
            tenant_id=tid_a,
            actor_id=actor,
            category="override_added",
            summary="A side",
            detail={},
        )
        await emit_audit_event(
            session,
            tenant_id=tid_b,
            actor_id=actor,
            category="override_added",
            summary="B side",
            detail={},
        )
        await session.commit()

    async with session_factory() as session:
        a_rows = (
            (await session.execute(select(StrategistActivityEvent).where(StrategistActivityEvent.tenant_id == tid_a)))
            .scalars()
            .all()
        )
        b_rows = (
            (await session.execute(select(StrategistActivityEvent).where(StrategistActivityEvent.tenant_id == tid_b)))
            .scalars()
            .all()
        )
    assert [r.summary for r in a_rows] == ["A side"]
    assert [r.summary for r in b_rows] == ["B side"]
