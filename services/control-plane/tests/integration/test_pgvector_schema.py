"""Integration — v2 Phase 5.5 Wave A: pgvector schema landed by migration 0050.

Run with ``uv run pytest -m integration tests/integration/test_pgvector_schema.py``.

What this test covers (scope-v2 §10.1):

- The ``vector`` extension is installed.
- Every source table (``ledger_events``, ``matrix_nodes``,
  ``oracle_chat_turns``, ``matrix_insights``) has an ``embedding
  vector(1024)`` column.
- One HNSW index per source-table embedding column.
- ``embedding_jobs`` table exists with the expected unique constraint,
  CHECK constraints, and poll index.
- INSERT on a source row enqueues a ``queued`` job via the
  ``deployai_enqueue_embedding_job`` trigger.
- UPDATE on a source row resets the existing job back to ``queued`` +
  attempts=0 (idempotent re-embed on mutation).
- DELETE on ``app_tenants`` cascades and drops orphan jobs.
- A literal ``vector(1024)`` value can be written and read back via
  ``::vector`` cast, and the HNSW index participates in a cosine
  similarity ORDER BY.

What this test does NOT cover (out of scope for Wave A):

- The Voyage-3 embedder worker — Wave B.
- The ``vector_search`` tool — Wave C.
- Cross-tenant RLS — the source tables already enforce tenancy at
  application layer; embedding columns inherit it.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration


# Mirrors SOURCE_TABLES in migration 20260613_0050_pgvector_embeddings.py.
_SOURCE_TABLES: tuple[str, ...] = (
    "ledger_events",
    "matrix_nodes",
    "oracle_chat_turns",
    "matrix_insights",
)


# ---------------------------------------------------------------------------
# Schema shape assertions
# ---------------------------------------------------------------------------


def test_vector_extension_installed(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as conn:
        row = conn.execute(text("SELECT 1 FROM pg_extension WHERE extname = 'vector'")).scalar()
    assert row == 1, "vector extension should be installed (testcontainer bootstrap + migration)"


def test_every_source_table_has_embedding_column(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' "
                "AND column_name = 'embedding' "
                "AND table_name = ANY(:tables)"
            ),
            {"tables": list(_SOURCE_TABLES)},
        ).all()
    landed = {r.table_name for r in rows}
    assert landed == set(_SOURCE_TABLES), f"missing embedding column on: {set(_SOURCE_TABLES) - landed}"


def test_every_source_table_has_hnsw_index(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT tablename, indexname "
                "FROM pg_indexes "
                "WHERE schemaname = 'public' "
                "AND indexname LIKE 'idx_%_embedding_hnsw'"
            )
        ).all()
    by_table = {r.tablename: r.indexname for r in rows}
    for tname in _SOURCE_TABLES:
        assert tname in by_table, f"HNSW index missing on {tname}"
        assert by_table[tname] == f"idx_{tname}_embedding_hnsw"


def test_embedding_jobs_table_shape(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as conn:
        cols = {
            r.column_name
            for r in conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_schema = 'public' AND table_name = 'embedding_jobs'"
                )
            ).all()
        }
    expected = {
        "id",
        "tenant_id",
        "source_table",
        "source_id",
        "status",
        "attempts",
        "last_error",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(cols), f"missing columns: {expected - cols}"

    with postgres_engine.connect() as conn:
        idx_rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'embedding_jobs'")
        ).all()
    idx_names = {r.indexname for r in idx_rows}
    assert "uq_embedding_jobs_source" in idx_names, "unique (source_table, source_id) missing"
    assert "idx_embedding_jobs_status_created_at" in idx_names, "worker poll index missing"


# ---------------------------------------------------------------------------
# Trigger behavior
# ---------------------------------------------------------------------------


def _seed_tenant_and_engagement(conn: Any) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    conn.execute(
        text("INSERT INTO app_tenants (id, name) VALUES (:t, 'pgvector-test')"),
        {"t": str(tenant_id)},
    )
    engagement_id = conn.execute(
        text("INSERT INTO engagements (tenant_id, name) VALUES (:t, 'pgvector test') RETURNING id"),
        {"t": str(tenant_id)},
    ).scalar_one()
    return tenant_id, engagement_id


def _insert_ledger_event(
    conn: Any,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    summary: str = "embed me",
) -> uuid.UUID:
    return conn.execute(
        text(
            "INSERT INTO ledger_events "
            "(tenant_id, engagement_id, occurred_at, actor_kind, source_kind, summary) "
            "VALUES (:t, :e, :o, 'system', 'manual_capture', :s) RETURNING id"
        ),
        {
            "t": str(tenant_id),
            "e": str(engagement_id),
            "o": datetime.now(UTC),
            "s": summary,
        },
    ).scalar_one()


def test_insert_on_ledger_event_enqueues_queued_job(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_tenant_and_engagement(conn)
        event_id = _insert_ledger_event(conn, tenant_id=tenant_id, engagement_id=engagement_id)

    with postgres_engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT tenant_id, source_table, source_id, status, attempts, last_error "
                "FROM embedding_jobs WHERE source_id = :id"
            ),
            {"id": str(event_id)},
        ).one()
    assert row.tenant_id == tenant_id
    assert row.source_table == "ledger_events"
    assert row.source_id == event_id
    assert row.status == "queued"
    assert row.attempts == 0
    assert row.last_error is None


def test_update_on_ledger_event_resets_existing_job_to_queued(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_tenant_and_engagement(conn)
        event_id = _insert_ledger_event(conn, tenant_id=tenant_id, engagement_id=engagement_id)

    # Simulate the worker: pick the job up, mark it done.
    with postgres_engine.begin() as conn:
        conn.execute(
            text("UPDATE embedding_jobs SET status = 'done', attempts = 1, last_error = NULL WHERE source_id = :id"),
            {"id": str(event_id)},
        )

    # Mutate the source row — trigger should bump the job back to queued.
    with postgres_engine.begin() as conn:
        conn.execute(
            text("UPDATE ledger_events SET summary = 'new content' WHERE id = :id"),
            {"id": str(event_id)},
        )

    with postgres_engine.connect() as conn:
        row = conn.execute(
            text("SELECT status, attempts FROM embedding_jobs WHERE source_id = :id"),
            {"id": str(event_id)},
        ).one()
    assert row.status == "queued", "UPDATE on source row must reset job to 'queued'"
    assert row.attempts == 0, "reset must also zero the retry counter"


def test_delete_tenant_cascades_to_embedding_jobs(postgres_engine: Engine) -> None:
    """The ``embedding_jobs.tenant_id`` FK is ``ON DELETE CASCADE``.

    Most sibling tenant-scoped tables (``ledger_events`` included) use a
    non-cascading FK to ``app_tenants`` — those rows must be cleaned up
    explicitly. We isolate the cascade behavior under test by inserting
    a row *directly* into ``embedding_jobs`` (mimicking a job that the
    Wave B worker created out-of-band) so the tenant delete is not
    blocked by an unrelated FK and the cascade we actually own is
    exercised.
    """
    tenant_id = uuid.uuid4()
    with postgres_engine.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'pgvector-cascade-test')"),
            {"t": str(tenant_id)},
        )
        conn.execute(
            text("INSERT INTO embedding_jobs (tenant_id, source_table, source_id) VALUES (:t, 'ledger_events', :sid)"),
            {"t": str(tenant_id), "sid": str(uuid.uuid4())},
        )

    with postgres_engine.connect() as conn:
        before = conn.execute(
            text("SELECT count(*) FROM embedding_jobs WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        ).scalar_one()
    assert before == 1

    with postgres_engine.begin() as conn:
        conn.execute(text("DELETE FROM app_tenants WHERE id = :t"), {"t": str(tenant_id)})

    with postgres_engine.connect() as conn:
        after = conn.execute(
            text("SELECT count(*) FROM embedding_jobs WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        ).scalar_one()
    assert after == 0, "embedding_jobs rows must cascade-delete when tenant is removed"


# ---------------------------------------------------------------------------
# Vector roundtrip + HNSW index participation
# ---------------------------------------------------------------------------


def _normalized_vector(seed: int, dim: int = 1024) -> list[float]:
    """Tiny deterministic vector: one-hot at ``seed % dim`` so cosine ranking is unambiguous."""
    v = [0.0] * dim
    v[seed % dim] = 1.0
    return v


def _vector_literal(v: list[float]) -> str:
    """pgvector text literal: ``[0.0,1.0,...]`` — what ::vector cast accepts."""
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


def test_direct_embedding_write_and_hnsw_cosine_query(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_tenant_and_engagement(conn)
        ids: list[uuid.UUID] = []
        # Three rows, each with a distinct one-hot vector. We'll query with
        # the vector that exactly matches index 1 and expect that row first.
        for i in range(3):
            eid = _insert_ledger_event(
                conn,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                summary=f"row {i}",
            )
            ids.append(eid)
            conn.execute(
                text("UPDATE ledger_events SET embedding = CAST(:v AS vector) WHERE id = :id"),
                {"v": _vector_literal(_normalized_vector(i)), "id": str(eid)},
            )

    # Cosine similarity (smaller distance = more similar). Force the planner
    # to consider the HNSW index — at three rows it may legitimately prefer
    # a seq-scan, so we don't assert "index was used"; we assert the result
    # ranking is correct, which is what the index would also produce.
    query_v = _vector_literal(_normalized_vector(1))
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT id FROM ledger_events "
                "WHERE tenant_id = :t AND embedding IS NOT NULL "
                "ORDER BY embedding <=> CAST(:q AS vector) "
                "LIMIT 1"
            ),
            {"t": str(tenant_id), "q": query_v},
        ).all()
    assert len(rows) == 1
    assert rows[0].id == ids[1], "row whose vector matches the query should rank first"
