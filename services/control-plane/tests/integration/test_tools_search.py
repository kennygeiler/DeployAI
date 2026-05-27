"""Integration: ``keyword_search`` + ``vector_search`` placeholder."""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.tools.search import keyword_search, vector_search
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
        c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'sr-test')"), {"t": str(tid)})
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'sr-eng', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tid)},
        )
        ev_id = uuid.uuid4()
        c.execute(
            text(
                "INSERT INTO ledger_events (id, tenant_id, engagement_id, occurred_at, "
                "actor_kind, actor_id, source_kind, source_ref, summary, detail) "
                "VALUES (:id, :t, :e, :occ, 'user', NULL, 'audit_other', NULL, "
                "        'Active Directory migration approved', CAST(:d AS jsonb))"
            ),
            {
                "id": str(ev_id),
                "t": str(tid),
                "e": str(eid),
                "occ": datetime(2026, 5, 1, tzinfo=UTC),
                "d": json.dumps({}),
            },
        )
        node_id = uuid.uuid4()
        c.execute(
            text(
                "INSERT INTO matrix_nodes "
                "  (id, tenant_id, engagement_id, node_type, title, attributes, evidence_event_ids) "
                "VALUES (:i, :t, :e, 'decision', 'Active Directory migration', "
                "        '{}'::jsonb, '{}'::uuid[])"
            ),
            {"i": str(node_id), "t": str(tid), "e": str(eid)},
        )
    yield {"tenant_id": tid, "engagement_id": eid, "event_id": ev_id, "node_id": node_id}


@pytest.mark.asyncio
async def test_keyword_search_returns_event_and_node_hits(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        result = await keyword_search(session, tenant_id=tid, engagement_id=eid, query="active directory")
        await session.commit()
        kinds = {r["kind"] for r in result.rows}
        assert "event" in kinds
        assert "node" in kinds


@pytest.mark.asyncio
async def test_keyword_search_filters_by_kinds(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        only_events = await keyword_search(
            session,
            tenant_id=tid,
            engagement_id=eid,
            query="active directory",
            kinds=["event"],
        )
        await session.commit()
        assert all(r["kind"] == "event" for r in only_events.rows)


@pytest.mark.asyncio
async def test_keyword_search_rejects_empty_query(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    from control_plane.agents.tools import ToolError

    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        with pytest.raises(ToolError):
            await keyword_search(session, tenant_id=tid, engagement_id=eid, query="   ")
        await session.rollback()


@pytest.mark.asyncio
async def test_vector_search_returns_empty_when_unembedded(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """Phase 5.5 Wave C: vector_search returns empty + non-truncated when no embeddings exist.

    Pre-Wave-A the source tables don't even carry an ``embedding``
    column; the tool detects this via :class:`ProgrammingError` and
    surfaces an empty hit list so the agent loop falls back to
    ``keyword_search``. Post-Wave-A but pre-Wave-B (column exists,
    rows unembedded) the same outcome holds via ``embedding IS NOT NULL``.
    """

    class _StubEmbedder:
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.0] * 1024 for _ in texts]

    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        result = await vector_search(
            session,
            tenant_id=tid,
            engagement_id=eid,
            query="anything",
            embedder=_StubEmbedder(),
        )
        await session.commit()
        assert result.rows == []
        # No overflow when there are no hits; truncated flag is reserved
        # for the "more hits than limit" signal.
        assert result.truncated is False
        assert result.detail is not None
        assert "vector_search" in result.detail
