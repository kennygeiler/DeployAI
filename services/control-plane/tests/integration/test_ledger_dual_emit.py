"""End-to-end: ``emit_audit_event`` writes an audit row AND a ledger row in
one transaction; rollback drops both (Phase F1.b)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from control_plane.audit import emit_audit_event
from control_plane.domain.ledger import LedgerEvent
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
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'ledger-dual-emit')"),
            {"t": str(tid)},
        )
    return tid


@pytest.mark.asyncio
async def test_audit_emit_also_writes_ledger_row(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    aid = uuid.uuid4()
    ref = uuid.uuid4()

    async with session_factory() as session:
        await emit_audit_event(
            session,
            tenant_id=tid,
            actor_id=aid,
            category="tenant.webhook.created",
            summary="webhook created via test",
            detail={"webhook_id": str(uuid.uuid4()), "signing_secret": "shh-leak"},
            ref_id=ref,
        )
        await session.commit()

    async with session_factory() as session:
        audit_rows = (
            (await session.execute(select(StrategistActivityEvent).where(StrategistActivityEvent.tenant_id == tid)))
            .scalars()
            .all()
        )
        ledger_rows = (await session.execute(select(LedgerEvent).where(LedgerEvent.tenant_id == tid))).scalars().all()

    assert len(audit_rows) == 1
    assert len(ledger_rows) == 1
    ledger = ledger_rows[0]
    assert ledger.source_kind == "settings_change"
    assert ledger.actor_kind == "user"
    assert ledger.actor_id == str(aid)
    assert ledger.source_ref == ref
    assert ledger.summary == "webhook created via test"
    assert ledger.detail.get("audit_category") == "tenant.webhook.created"
    # secret-shaped keys must NOT leak through into the ledger
    assert "signing_secret" not in ledger.detail


@pytest.mark.asyncio
async def test_rollback_drops_both_rows(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    aid = uuid.uuid4()

    async with session_factory() as session:
        await emit_audit_event(
            session,
            tenant_id=tid,
            actor_id=aid,
            category="break_glass.requested",
            summary="bg requested then rolled back",
            detail={},
        )
        await session.rollback()

    async with session_factory() as session:
        audit_rows = (
            (await session.execute(select(StrategistActivityEvent).where(StrategistActivityEvent.tenant_id == tid)))
            .scalars()
            .all()
        )
        ledger_rows = (await session.execute(select(LedgerEvent).where(LedgerEvent.tenant_id == tid))).scalars().all()
    assert audit_rows == []
    assert ledger_rows == []


@pytest.mark.asyncio
async def test_unknown_audit_category_falls_back_to_audit_other(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)
    async with session_factory() as session:
        await emit_audit_event(
            session,
            tenant_id=tid,
            actor_id=uuid.uuid4(),
            category="something.unmapped",
            summary="novel category test",
            detail={},
        )
        await session.commit()

    async with session_factory() as session:
        ledger_rows = (await session.execute(select(LedgerEvent).where(LedgerEvent.tenant_id == tid))).scalars().all()
    assert len(ledger_rows) == 1
    assert ledger_rows[0].source_kind == "audit_other"
