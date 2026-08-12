"""Integration cross-check for the derived ground truth (ticket G2).

Seeds BlueState-XL into the shared pgvector testcontainer via the official
runner, then verifies that a sample of derived expected strings and
citation UUIDs actually exist in the seeded database — i.e. the
introspection side channel and the emitted SQL cannot silently drift.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from control_plane.scenarios.bluestate_xl import ENGAGEMENT_ID, TENANT_ID
from control_plane.scenarios.bluestate_xl.runner import apply_bluestate_xl_scenario

from .derive import derive_questions
from .types import Question

pytestmark = pytest.mark.integration


def _async_url(engine: Engine) -> str:
    return engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def seeded_engine(postgres_engine: Engine) -> AsyncIterator[AsyncEngine]:
    """Seed BlueState-XL (snapshots skipped — this test reads raw rows)."""
    engine: AsyncEngine = create_async_engine(_async_url(postgres_engine))
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        await apply_bluestate_xl_scenario(
            session,
            tenant_id=uuid.UUID(TENANT_ID),
            skip_snapshots=True,
        )
        await session.commit()
    try:
        yield engine
    finally:
        await engine.dispose()


def _sample_per_template(n: int = 3) -> list[Question]:
    """First ``n`` factual questions of each template (deterministic)."""
    by_template: dict[str, list[Question]] = {}
    for q in derive_questions():
        if q.should_idk:
            continue
        bucket = by_template.setdefault(q.template or "untagged", [])
        if len(bucket) < n:
            bucket.append(q)
    return [q for bucket in by_template.values() for q in bucket]


async def _id_exists(engine: AsyncEngine, raw_id: str) -> bool:
    """True when the UUID resolves in any citable seeded table."""
    async with engine.connect() as conn:
        for table in ("ledger_events", "matrix_nodes", "matrix_insights"):
            row = await conn.execute(
                text(
                    f"SELECT 1 FROM {table} "  # table name from a fixed tuple, not user input
                    "WHERE id = CAST(:id AS uuid) AND engagement_id = CAST(:eid AS uuid)"
                ),
                {"id": raw_id, "eid": ENGAGEMENT_ID},
            )
            if row.first() is not None:
                return True
    return False


async def test_derived_citation_ids_exist_in_seeded_db(seeded_engine: AsyncEngine) -> None:
    sample = _sample_per_template()
    assert sample, "sampler produced no factual questions"
    missing: list[str] = []
    for q in sample:
        for raw_id in q.expected_citation_ids:
            if not await _id_exists(seeded_engine, raw_id):
                missing.append(f"{q.id}: {raw_id}")
    assert not missing, f"derived citation ids absent from seeded DB: {missing}"


async def test_derived_expected_strings_exist_in_seeded_db(seeded_engine: AsyncEngine) -> None:
    """Every sampled expected substring must appear in seeded node titles,
    insight titles, or ledger summaries — otherwise the question would be
    unanswerable even by a perfect agent."""
    sample = _sample_per_template()
    misses: list[str] = []
    async with seeded_engine.connect() as conn:
        for q in sample:
            for needle in q.expected_answer_contains:
                # Risk-status verdict words are derived facts (open/resolved
                # column state), not literal strings — check the column.
                if q.template == "risk_status" and needle in ("open", "resolved"):
                    status_row = await conn.execute(
                        text(
                            "SELECT status FROM matrix_insights "
                            "WHERE id = CAST(:id AS uuid) AND engagement_id = CAST(:eid AS uuid)"
                        ),
                        {"id": q.expected_citation_ids[0], "eid": ENGAGEMENT_ID},
                    )
                    status = status_row.scalar()
                    expected_status = "resolved" if needle == "resolved" else "open"
                    if status != expected_status:
                        misses.append(f"{q.id}: insight status {status!r} != {expected_status!r}")
                    continue
                row = await conn.execute(
                    text(
                        "SELECT 1 WHERE EXISTS ("
                        "  SELECT 1 FROM matrix_nodes"
                        "  WHERE engagement_id = CAST(:eid AS uuid) AND title ILIKE :pat"
                        ") OR EXISTS ("
                        "  SELECT 1 FROM matrix_insights"
                        "  WHERE engagement_id = CAST(:eid AS uuid) AND title ILIKE :pat"
                        ") OR EXISTS ("
                        "  SELECT 1 FROM ledger_events"
                        "  WHERE engagement_id = CAST(:eid AS uuid) AND summary ILIKE :pat"
                        ")"
                    ),
                    {"eid": ENGAGEMENT_ID, "pat": f"%{needle}%"},
                )
                if row.first() is None:
                    misses.append(f"{q.id}: {needle!r}")
    assert not misses, f"derived expected strings absent from seeded DB: {misses}"
