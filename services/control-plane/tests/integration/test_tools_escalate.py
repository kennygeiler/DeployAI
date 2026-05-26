"""Integration: ``propose_action`` — the only write tool in Phase 1.

Assert that one call inserts one queue row + emits a ``propose_action``
ledger event in addition to the ``agent_tool_invocation`` audit emit.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Generator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.tools import ToolError
from control_plane.agents.tools.escalate import propose_action
from control_plane.db import clear_engine_cache, get_app_db_session

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def app_session(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    clear_engine_cache()
    try:
        yield None
    finally:
        clear_engine_cache()


@pytest.fixture
def seeded(postgres_engine: Engine) -> Generator[dict[str, uuid.UUID]]:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    with postgres_engine.begin() as c:
        c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'esc-test')"), {"t": str(tid)})
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'esc-eng', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tid)},
        )
    yield {"tenant_id": tid, "engagement_id": eid}


@pytest.mark.asyncio
async def test_propose_action_inserts_queue_row_and_emits_ledger(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    node_ref = uuid.uuid4()
    event_ref = uuid.uuid4()
    async for session in get_app_db_session():
        result = await propose_action(
            session,
            tenant_id=tid,
            engagement_id=eid,
            description="Confirm sponsor's headcount commitment",
            priority="high",
            phase="P2_active",
            evidence_node_ids=[str(node_ref)],
            evidence_event_ids=[str(event_ref)],
            rationale="Two open risks point at this node.",
        )
        await session.commit()
        assert result.rows[0]["priority"] == "high"
        item_id = result.rows[0]["action_queue_item_id"]
        assert item_id.startswith("kenny-")

    with postgres_engine.connect() as c:
        queue_count = c.execute(
            text(
                "SELECT count(*) FROM strategist_action_queue_items "
                "WHERE tenant_id = :t AND engagement_id = :e AND status = 'pending'"
            ),
            {"t": str(tid), "e": str(eid)},
        ).scalar_one()
        assert queue_count == 1

        propose_count = c.execute(
            text("SELECT count(*) FROM ledger_events WHERE tenant_id = :t AND source_kind = 'propose_action'"),
            {"t": str(tid)},
        ).scalar_one()
        assert propose_count == 1

        invoc_count = c.execute(
            text("SELECT count(*) FROM ledger_events WHERE tenant_id = :t AND source_kind = 'agent_tool_invocation'"),
            {"t": str(tid)},
        ).scalar_one()
        assert invoc_count == 1


@pytest.mark.asyncio
async def test_propose_action_rejects_unknown_priority(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        with pytest.raises(ToolError):
            await propose_action(
                session,
                tenant_id=tid,
                engagement_id=eid,
                description="x",
                priority="superhigh",
            )
        await session.rollback()


@pytest.mark.asyncio
async def test_propose_action_rejects_empty_description(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        with pytest.raises(ToolError):
            await propose_action(
                session,
                tenant_id=tid,
                engagement_id=eid,
                description="   ",
                priority="medium",
            )
        await session.rollback()
