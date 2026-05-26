"""v2 Phase 5 Wave 2F — outbound-MCP kill switch (threat-model §5.5 Option B).

Covers:
  - Migration default: ``app_tenants.mcp_outbound_disabled`` is False
    for newly-inserted rows (server_default applies).
  - Admin write path: ``set_mcp_outbound_disabled(True)`` flips the
    column AND emits a ledger row of source_kind
    ``mcp_outbound_killswitch_changed`` with the expected detail.
  - Hot path: ``DbMcpKillSwitch.is_outbound_disabled(tid)`` reflects
    the flip on a fresh cache.
  - Cache TTL: a flip within the 5s window is invisible until expiry;
    after expiry the next read picks up the new value.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from control_plane.agents.agent_kenny.mcp_kill_switch import DbMcpKillSwitch
from control_plane.agents.agent_kenny.mcp_kill_switch_admin import set_mcp_outbound_disabled
from control_plane.domain.ledger import LedgerEvent

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


def _seed_tenant(eng: Engine, name: str = "killswitch-test") -> uuid.UUID:
    tid = uuid.uuid4()
    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"),
            {"t": str(tid), "n": name},
        )
    return tid


@pytest.mark.asyncio
async def test_default_false_after_migration(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)

    # Direct SQL: confirm the server_default applied — important because
    # the AppTenant.default=False would mask a missing server_default
    # for ORM inserts, but the raw INSERT above goes around the ORM.
    with postgres_engine.begin() as conn:
        row = conn.execute(
            text("SELECT mcp_outbound_disabled FROM app_tenants WHERE id = :t"),
            {"t": str(tid)},
        ).scalar_one()
    assert row is False

    ks = DbMcpKillSwitch(session_factory)
    assert (await ks.is_outbound_disabled(tid)) is False


@pytest.mark.asyncio
async def test_set_mcp_outbound_disabled_flips_column_and_emits_audit(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)

    async with session_factory() as session:
        await set_mcp_outbound_disabled(
            session,
            tenant_id=tid,
            disabled=True,
            actor_id="on-call-sre",
        )
        await session.commit()

    # Column flipped.
    with postgres_engine.begin() as conn:
        row = conn.execute(
            text("SELECT mcp_outbound_disabled FROM app_tenants WHERE id = :t"),
            {"t": str(tid)},
        ).scalar_one()
    assert row is True

    # Ledger row landed with the right source_kind + detail.
    async with session_factory() as session:
        rows = (await session.execute(select(LedgerEvent).where(LedgerEvent.tenant_id == tid))).scalars().all()
    assert len(rows) == 1
    ev = rows[0]
    assert ev.source_kind == "mcp_outbound_killswitch_changed"
    assert ev.actor_kind == "user"
    assert ev.actor_id == "on-call-sre"
    assert ev.detail == {"disabled": True, "actor_id": "on-call-sre"}
    assert "ENGAGED" in ev.summary


@pytest.mark.asyncio
async def test_killswitch_reads_true_after_flip_on_fresh_cache(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    tid = _seed_tenant(postgres_engine)

    async with session_factory() as session:
        await set_mcp_outbound_disabled(session, tenant_id=tid, disabled=True, actor_id="tester")
        await session.commit()

    # Fresh kill switch — no cached entry — reads through to DB.
    ks = DbMcpKillSwitch(session_factory)
    assert (await ks.is_outbound_disabled(tid)) is True


@pytest.mark.asyncio
async def test_cache_ttl_hides_flip_then_picks_it_up(
    postgres_engine: Engine,
    session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """5s TTL: a flip within the window is invisible; after expiry it lands."""
    tid = _seed_tenant(postgres_engine)

    # Drive the clock by hand so the test is deterministic + fast.
    fake_now = {"t": 1000.0}

    def fake_clock() -> float:
        return fake_now["t"]

    ks = DbMcpKillSwitch(session_factory, cache_ttl_seconds=5.0, clock=fake_clock)

    # Initial state: disabled=False, cached.
    assert (await ks.is_outbound_disabled(tid)) is False

    # Flip to True under the cache window.
    async with session_factory() as session:
        await set_mcp_outbound_disabled(session, tenant_id=tid, disabled=True, actor_id="tester")
        await session.commit()

    # Within 5s: still cached as False.
    fake_now["t"] += 1.0
    assert (await ks.is_outbound_disabled(tid)) is False

    # Past the TTL: refetch picks up the new value.
    fake_now["t"] += 10.0
    assert (await ks.is_outbound_disabled(tid)) is True

    # A second flip back inside the new window stays cached as True.
    async with session_factory() as session:
        await set_mcp_outbound_disabled(session, tenant_id=tid, disabled=False, actor_id="tester")
        await session.commit()
    fake_now["t"] += 1.0
    assert (await ks.is_outbound_disabled(tid)) is True

    # Expire again — and the False is picked up.
    fake_now["t"] += 10.0
    assert (await ks.is_outbound_disabled(tid)) is False

    # Two ledger rows in total — one for each call to
    # ``set_mcp_outbound_disabled`` (True then False). The cache TTL has
    # zero effect on emit: emit happens unconditionally on the write
    # side; the cache only suppresses the *read* side.
    async with session_factory() as session:
        rows = (
            (
                await session.execute(
                    select(LedgerEvent)
                    .where(LedgerEvent.tenant_id == tid)
                    .where(LedgerEvent.source_kind == "mcp_outbound_killswitch_changed")
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 2
