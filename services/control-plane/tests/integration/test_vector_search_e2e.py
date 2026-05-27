"""End-to-end ``vector_search`` against a real pgvector testcontainer.

The test exercises the full path Wave C ships:

    embed_query (stubbed)
      -> SQL bind with cosine ``<=>`` operator
      -> HNSW-eligible cosine distance scan
      -> score = 1 - distance, sorted desc

Wave A's migration adds the ``embedding vector(1024)`` column on
``ledger_events``; until that migration is merged, this entire module
is skipped (the column doesn't exist, so the seed step would fail with
``UndefinedColumn``). Skipping at module level instead of catching the
exception per-test keeps the failure mode unambiguous in CI: either
Wave A is present and the assertions run, or the module is reported
as skipped.

The query "vector" is deterministic dummy data, not the output of a
real Voyage embedding, so the test is hermetic (no network) and
verifies the *ranking + scoping contract* — not the semantic quality
of any particular embedder.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.tools.search import vector_search
from control_plane.db import clear_engine_cache, get_app_db_session

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ledger_has_embedding_column(engine: Engine) -> bool:
    """Skip-marker: True iff Wave A's migration is present in this DB."""
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = 'ledger_events' AND column_name = 'embedding'"
            )
        ).first()
    return row is not None


@pytest.fixture(scope="module", autouse=True)
def _skip_if_wave_a_not_merged(postgres_engine: Engine) -> None:
    """Module-level guard: if Wave A's pgvector column is missing, skip."""
    if not _ledger_has_embedding_column(postgres_engine):
        pytest.skip(
            "ledger_events.embedding column not present — Wave A migration "
            "0048_pgvector_embeddings has not been merged in this env"
        )


@pytest_asyncio.fixture
async def app_session(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    clear_engine_cache()
    try:
        yield None
    finally:
        clear_engine_cache()


def _vec(seed: float) -> list[float]:
    """Build a 1024-dim deterministic dummy vector, mostly ``seed`` with a marker.

    The first slot carries a unique fingerprint so two vectors with
    different ``seed`` values yield different cosine distances when
    compared to a fixed query vector. The remaining 1023 slots are
    constant so the test rows look "in the same neighborhood" of each
    other.
    """
    base = [0.01] * 1024
    base[0] = float(seed)
    return base


def _vec_literal(v: list[float]) -> str:
    return "[" + ",".join(repr(float(x)) for x in v) + "]"


@pytest.fixture
def seeded(postgres_engine: Engine) -> Generator[dict[str, uuid.UUID]]:
    """Seed three ledger events with hand-tuned distance to a known query.

    The query vector ``_vec(1.0)`` matches ``ev_close`` (also seeded with
    ``1.0``) most strongly, ``ev_mid`` next, and ``ev_far`` last. A
    *foreign tenant* row with the closest possible vector confirms the
    tenant filter strips it from the result regardless of similarity.
    """
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    foreign_tid = uuid.uuid4()
    foreign_eid = uuid.uuid4()
    ev_close = uuid.uuid4()
    ev_mid = uuid.uuid4()
    ev_far = uuid.uuid4()
    ev_foreign = uuid.uuid4()

    with postgres_engine.begin() as c:
        for t, name in ((tid, "vs-e2e-self"), (foreign_tid, "vs-e2e-foreign")):
            c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, :n)"), {"t": str(t), "n": name})
        for t, e, name in ((tid, eid, "vs-eng"), (foreign_tid, foreign_eid, "vs-foreign-eng")):
            c.execute(
                text(
                    "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                    "VALUES (:i, :t, :n, 'P1_pre_engagement', 'active')"
                ),
                {"i": str(e), "t": str(t), "n": name},
            )

        def _insert(eid_: uuid.UUID, tid_: uuid.UUID, ev_id: uuid.UUID, summary: str, vec_seed: float) -> None:
            c.execute(
                text(
                    "INSERT INTO ledger_events "
                    "  (id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id, "
                    "   source_kind, source_ref, summary, detail, embedding) "
                    "VALUES (:id, :t, :e, :occ, 'user', NULL, 'audit_other', NULL, "
                    "        :sum, CAST(:d AS jsonb), CAST(:emb AS vector))"
                ),
                {
                    "id": str(ev_id),
                    "t": str(tid_),
                    "e": str(eid_),
                    "occ": datetime(2026, 5, 1, tzinfo=UTC),
                    "sum": summary,
                    "d": json.dumps({}),
                    "emb": _vec_literal(_vec(vec_seed)),
                },
            )

        _insert(eid, tid, ev_close, "Active Directory migration concerns", 1.0)
        _insert(eid, tid, ev_mid, "Kerberos delegation question", 0.5)
        _insert(eid, tid, ev_far, "Random unrelated note", -0.5)
        _insert(foreign_eid, foreign_tid, ev_foreign, "FOREIGN AD note — must not surface", 1.0)

        # A no-embedding row in the same engagement: filter must drop it
        # without erroring.
        c.execute(
            text(
                "INSERT INTO ledger_events "
                "  (id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id, "
                "   source_kind, source_ref, summary, detail) "
                "VALUES (:id, :t, :e, :occ, 'user', NULL, 'audit_other', NULL, "
                "        :sum, CAST(:d AS jsonb))"
            ),
            {
                "id": str(uuid.uuid4()),
                "t": str(tid),
                "e": str(eid),
                "occ": datetime(2026, 5, 2, tzinfo=UTC),
                "sum": "Unembedded backlog row",
                "d": json.dumps({}),
            },
        )

    yield {
        "tenant_id": tid,
        "engagement_id": eid,
        "ev_close": ev_close,
        "ev_mid": ev_mid,
        "ev_far": ev_far,
        "ev_foreign": ev_foreign,
        "foreign_tenant_id": foreign_tid,
        "foreign_engagement_id": foreign_eid,
    }


class _FixedEmbedder:
    """Returns a fixed vector regardless of the query text."""

    def __init__(self, vec: list[float]) -> None:
        self._vec = vec

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [list(self._vec) for _ in texts]


# --------------------------------------------------------------------------
# The headline assertion from scope-v2 §10.4: "active directory" returns
# the W19-W21 narrative events. Here we synthesize the same shape with
# deterministic vectors so the test holds without depending on a real
# embedder's output for a particular phrase.
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_returns_rows_ranked_by_similarity(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        result = await vector_search(
            session,
            tenant_id=tid,
            engagement_id=eid,
            query="active directory",
            kind="ledger",
            embedder=_FixedEmbedder(_vec(1.0)),
        )
        await session.commit()

    ids = [r["id"] for r in result.rows]
    # The unembedded backlog row must not appear.
    assert all(r["summary"] != "Unembedded backlog row" for r in result.rows)
    # ev_close (seed 1.0) is closest to the query vector (seed 1.0), then
    # ev_mid (0.5), then ev_far (-0.5).
    assert ids[0] == str(seeded["ev_close"])
    assert ids[1] == str(seeded["ev_mid"])
    assert ids[2] == str(seeded["ev_far"])
    # Score ordering is monotonic descending.
    scores = [r["score"] for r in result.rows]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_tenant_filter_blocks_foreign_rows(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        result = await vector_search(
            session,
            tenant_id=tid,
            engagement_id=eid,
            query="anything",
            kind="ledger",
            embedder=_FixedEmbedder(_vec(1.0)),
        )
        await session.commit()
    foreign_id = str(seeded["ev_foreign"])
    assert all(r["id"] != foreign_id for r in result.rows), (
        "tenant scope leaked: foreign tenant's row appeared in result"
    )


@pytest.mark.asyncio
async def test_engagement_scope_filters_other_engagements(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """An engagement_id from a foreign engagement must return zero hits."""
    tid = seeded["tenant_id"]
    foreign_eng = seeded["foreign_engagement_id"]
    async for session in get_app_db_session():
        result = await vector_search(
            session,
            tenant_id=tid,
            engagement_id=foreign_eng,
            query="active directory",
            kind="ledger",
            embedder=_FixedEmbedder(_vec(1.0)),
        )
        await session.commit()
    assert result.rows == []


@pytest.mark.asyncio
async def test_kind_none_merges_across_tables_without_error(
    app_session: None, postgres_engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    """With ``kind=None`` the tool queries all four tables.

    The matrix / insight / conversation tables are empty here, so the
    only contributions are the seeded ledger rows — but the merge code
    path must not error when the sibling tables return zero results
    (or even when their ``embedding`` columns are absent).
    """
    tid = seeded["tenant_id"]
    eid = seeded["engagement_id"]
    async for session in get_app_db_session():
        result = await vector_search(
            session,
            tenant_id=tid,
            engagement_id=eid,
            query="active directory",
            embedder=_FixedEmbedder(_vec(1.0)),
        )
        await session.commit()
    # All hits should be from the ledger; merged rank is by score desc.
    assert {r["kind"] for r in result.rows} == {"ledger"}
    assert result.rows[0]["id"] == str(seeded["ev_close"])
