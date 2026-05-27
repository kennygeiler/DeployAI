"""Integration — v2 Phase 5.5 Wave B: embedder worker tick end-to-end.

Seeds three ``ledger_events`` (Wave A's trigger auto-enqueues an
``embedding_jobs`` row per insert), runs one ``run_embedder_tick`` with a
stubbed Voyage client, and asserts:

- Every job ends ``status='done'`` with no ``last_error``.
- Every source row ends with a non-NULL 1024-dim ``embedding`` column.
- The Voyage stub was called once with the three summaries.

Skips gracefully if Wave A's migration hasn't landed (no ``embedding_jobs``
table). Once Wave A is on main this skip becomes a no-op.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from control_plane.agents.agent_kenny.embeddings.voyage_client import VOYAGE_DIM, VoyageEmbedder
from control_plane.workers.embedder import run_embedder_tick

pytestmark = pytest.mark.integration


def _embedding_jobs_present(engine: Engine) -> bool:
    """Wave A's migration may not be merged on this run; skip if so."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name = 'embedding_jobs'"
            )
        ).scalar()
    return row == 1


@pytest.fixture()
def _skip_unless_wave_a(postgres_engine: Engine) -> None:
    if not _embedding_jobs_present(postgres_engine):
        pytest.skip("Wave A's embedding_jobs table not present; rebase onto Wave A to unskip.")


def _async_url(postgres_engine: Engine) -> str:
    parsed = make_url(postgres_engine.url)
    return parsed.set(drivername="postgresql+asyncpg").render_as_string(hide_password=False)


def _seed_tenant_engagement(conn: Any) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    conn.execute(
        text("INSERT INTO app_tenants (id, name) VALUES (:t, 'embedder-e2e')"),
        {"t": str(tenant_id)},
    )
    engagement_id = conn.execute(
        text("INSERT INTO engagements (tenant_id, name) VALUES (:t, 'embedder e2e') RETURNING id"),
        {"t": str(tenant_id)},
    ).scalar_one()
    return tenant_id, engagement_id


def _seed_three_ledger_events(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> list[uuid.UUID]:
    summaries = ["sso migration started", "stakeholder approved", "go-live confirmed"]
    ids: list[uuid.UUID] = []
    with engine.begin() as conn:
        for s in summaries:
            ids.append(
                conn.execute(
                    text(
                        "INSERT INTO ledger_events "
                        "(tenant_id, engagement_id, occurred_at, actor_kind, source_kind, summary) "
                        "VALUES (:t, :e, :o, 'system', 'manual_capture', :s) RETURNING id"
                    ),
                    {
                        "t": str(tenant_id),
                        "e": str(engagement_id),
                        "o": datetime.now(UTC),
                        "s": s,
                    },
                ).scalar_one()
            )
    return ids


class _StubEmbedder(VoyageEmbedder):
    """Deterministic test double that bypasses the network."""

    def __init__(self) -> None:
        super().__init__(api_key="test-key")
        self.calls: list[list[str]] = []

    async def embed(self, texts: list[str]) -> list[list[float]]:
        self.calls.append(list(texts))
        # Distinct vector per input so we can assert per-row write-back later.
        return [[0.1 + (i / 1000.0)] * VOYAGE_DIM for i, _ in enumerate(texts)]


@pytest.mark.asyncio
async def test_embedder_tick_drains_three_seeded_ledger_events(
    postgres_engine: Engine,
    _skip_unless_wave_a: None,
) -> None:
    # Seed via the sync engine so the trigger runs in the same DB visible
    # to the async worker session below.
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_tenant_engagement(conn)
    event_ids = _seed_three_ledger_events(postgres_engine, tenant_id=tenant_id, engagement_id=engagement_id)

    # Verify Wave A's trigger enqueued three jobs (preconditions).
    with postgres_engine.connect() as conn:
        queued_before = conn.execute(
            text("SELECT count(*) FROM embedding_jobs WHERE source_id = ANY(:ids) AND status = 'queued'"),
            {"ids": [str(e) for e in event_ids]},
        ).scalar_one()
    assert queued_before == 3, "Wave A trigger should have enqueued one job per inserted row"

    # Drive one tick.
    stub = _StubEmbedder()
    engine = create_async_engine(_async_url(postgres_engine))
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            report = await run_embedder_tick(session, embedder=stub)
            await session.commit()
    finally:
        await engine.dispose()

    assert report.processed == 3
    assert report.succeeded == 3
    assert report.failed == 0
    assert report.by_source_table == {"ledger_events": 3}

    # Voyage stub got one batched call with the three summaries.
    assert len(stub.calls) == 1
    assert sorted(stub.calls[0]) == sorted(["sso migration started", "stakeholder approved", "go-live confirmed"])

    # Every job ends 'done' with no last_error.
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT status, last_error FROM embedding_jobs WHERE source_id = ANY(:ids)"),
            {"ids": [str(e) for e in event_ids]},
        ).all()
    assert len(rows) == 3
    assert all(r.status == "done" for r in rows)
    assert all(r.last_error is None for r in rows)

    # Every source row has a non-null 1024-dim embedding.
    with postgres_engine.connect() as conn:
        embedded = conn.execute(
            text(
                "SELECT id, vector_dims(embedding) AS dim FROM ledger_events "
                "WHERE id = ANY(:ids) AND embedding IS NOT NULL"
            ),
            {"ids": [str(e) for e in event_ids]},
        ).all()
    assert {r.id for r in embedded} == set(event_ids)
    assert all(r.dim == VOYAGE_DIM for r in embedded)


@pytest.mark.asyncio
async def test_embedder_tick_with_empty_queue_is_noop(
    postgres_engine: Engine,
    _skip_unless_wave_a: None,
) -> None:
    """No queued jobs → tick returns processed=0 without calling Voyage."""
    stub = _StubEmbedder()
    engine = create_async_engine(_async_url(postgres_engine))
    try:
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with maker() as session:
            report = await run_embedder_tick(session, embedder=stub)
            await session.commit()
    finally:
        await engine.dispose()

    assert report.processed == 0
    assert stub.calls == []
