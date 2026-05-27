"""Unit tests for ``run_embedder_tick`` (Phase 5.5 Wave B).

The worker runs raw SQL against Postgres-only types (``vector``, ``= ANY``)
so we can't drive it against sqlite. Instead these tests stub
``AsyncSession`` with a hand-rolled fake that scripts the SELECT / UPDATE
roundtrips. Integration coverage of the real SQL path lives in
``tests/integration/test_embedder_e2e.py``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock

import pytest

from control_plane.agents.agent_kenny.embeddings.voyage_client import VOYAGE_DIM, VoyageError
from control_plane.workers.embedder import (
    TRUNCATION_CAP_CHARS,
    EmbedderTickReport,
    run_embedder_tick,
)

# ---------------------------------------------------------------------------
# Fake AsyncSession
# ---------------------------------------------------------------------------


@dataclass
class _Result:
    """Mimics a tiny slice of the SQLAlchemy Result API."""

    rows: list[dict[str, Any]]

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self.rows


@dataclass
class _Call:
    sql_lower: str
    params: dict[str, Any]


@dataclass
class _FakeSession:
    """Records every ``execute`` and replies with the queued result."""

    queued_jobs: list[dict[str, Any]] = field(default_factory=list)
    source_rows: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    calls: list[_Call] = field(default_factory=list)
    job_state: dict[uuid.UUID, dict[str, Any]] = field(default_factory=dict)
    vector_writes: dict[tuple[str, uuid.UUID], list[float]] = field(default_factory=dict)

    async def execute(self, stmt: Any, params: dict[str, Any] | None = None) -> _Result:
        sql = str(stmt).lower()
        params = params or {}
        self.calls.append(_Call(sql_lower=sql, params=params))

        if "from embedding_jobs" in sql and "select" in sql:
            # Claim path. Return + mutate state so the next SELECT would
            # see them flipped to 'running' — but the worker only SELECTs once.
            for job in self.queued_jobs:
                self.job_state[job["id"]] = {
                    "status": "queued",
                    "attempts": job.get("attempts", 0),
                    "last_error": None,
                }
            return _Result(self.queued_jobs)

        if "update embedding_jobs" in sql and "status = 'running'" in sql:
            for job_id in params.get("ids", []):
                self.job_state[job_id]["status"] = "running"
                self.job_state[job_id]["attempts"] += 1
            return _Result([])

        if "update embedding_jobs" in sql and "status = 'done'" in sql:
            job_id = params["id"]
            self.job_state[job_id]["status"] = "done"
            self.job_state[job_id]["last_error"] = None
            return _Result([])

        if "update embedding_jobs" in sql and ":status" in sql:
            job_id = params["id"]
            self.job_state[job_id]["status"] = params["status"]
            self.job_state[job_id]["last_error"] = params["reason"]
            return _Result([])

        if (
            "from ledger_events" in sql
            or "from matrix_nodes" in sql
            or "from oracle_chat_turns" in sql
            or "from matrix_insights" in sql
        ):
            table = next(t for t in self.source_rows if t in sql)
            ids = set(params.get("ids", []))
            return _Result([r for r in self.source_rows[table] if r["id"] in ids])

        if "update " in sql and "set embedding" in sql:
            # Capture which table this update was for.
            table = next(
                t
                for t in ("ledger_events", "matrix_nodes", "oracle_chat_turns", "matrix_insights")
                if f"update {t}" in sql
            )
            self.vector_writes[(table, params["id"])] = params["vec"]
            return _Result([])

        return _Result([])

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_three_ledger_jobs(session: _FakeSession) -> list[uuid.UUID]:
    """Seed three queued ledger_events jobs with matching source rows."""
    job_ids = [uuid.uuid4() for _ in range(3)]
    source_ids = [uuid.uuid4() for _ in range(3)]
    summaries = ["hello world", "second event", "third event"]

    session.queued_jobs = [
        {
            "id": job_ids[i],
            "source_table": "ledger_events",
            "source_id": source_ids[i],
            "attempts": 0,
        }
        for i in range(3)
    ]
    session.source_rows["ledger_events"] = [{"id": source_ids[i], "summary": summaries[i]} for i in range(3)]
    return job_ids


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_tick_empty_queue_returns_zero_report() -> None:
    session = _FakeSession()
    embedder = AsyncMock()

    report = await run_embedder_tick(session, embedder=embedder)

    assert isinstance(report, EmbedderTickReport)
    assert report.processed == 0
    assert report.succeeded == 0
    assert report.failed == 0
    embedder.embed.assert_not_called()


@pytest.mark.asyncio
async def test_tick_happy_path_writes_vectors_and_marks_done() -> None:
    session = _FakeSession()
    job_ids = _seed_three_ledger_jobs(session)

    embedder = AsyncMock()
    embedder.embed.return_value = [[0.5] * VOYAGE_DIM for _ in range(3)]

    report = await run_embedder_tick(session, embedder=embedder)

    assert report.processed == 3
    assert report.succeeded == 3
    assert report.failed == 0
    assert report.by_source_table == {"ledger_events": 3}
    # Voyage saw exactly the three summaries.
    embedder.embed.assert_awaited_once()
    sent_texts = embedder.embed.await_args.args[0]
    assert sorted(sent_texts) == ["hello world", "second event", "third event"]
    # Every job ends 'done'.
    for jid in job_ids:
        assert session.job_state[jid]["status"] == "done"
    # Every source row got a vector write.
    assert len(session.vector_writes) == 3


@pytest.mark.asyncio
async def test_tick_truncates_long_text_to_cap() -> None:
    session = _FakeSession()
    big = "x" * (TRUNCATION_CAP_CHARS + 5000)
    job_id = uuid.uuid4()
    src_id = uuid.uuid4()
    session.queued_jobs = [
        {
            "id": job_id,
            "source_table": "matrix_nodes",
            "source_id": src_id,
            "attempts": 0,
        }
    ]
    session.source_rows["matrix_nodes"] = [{"id": src_id, "title": "T", "description": big}]

    embedder = AsyncMock()
    embedder.embed.return_value = [[0.1] * VOYAGE_DIM]

    await run_embedder_tick(session, embedder=embedder)

    sent = embedder.embed.await_args.args[0][0]
    assert len(sent) == TRUNCATION_CAP_CHARS


@pytest.mark.asyncio
async def test_tick_voyage_failure_marks_job_queued_for_retry_below_max() -> None:
    """attempts=1 (< 5) → job goes back to 'queued', last_error populated."""
    session = _FakeSession()
    job_id = uuid.uuid4()
    src_id = uuid.uuid4()
    session.queued_jobs = [{"id": job_id, "source_table": "ledger_events", "source_id": src_id, "attempts": 0}]
    session.source_rows["ledger_events"] = [{"id": src_id, "summary": "x"}]

    embedder = AsyncMock()
    embedder.embed.side_effect = VoyageError("upstream 500")

    report = await run_embedder_tick(session, embedder=embedder, max_attempts=5)

    assert report.processed == 1
    assert report.succeeded == 0
    assert report.failed == 1
    state = session.job_state[job_id]
    assert state["status"] == "queued"
    assert "upstream 500" in (state["last_error"] or "")


@pytest.mark.asyncio
async def test_tick_voyage_failure_marks_failed_at_max_attempts() -> None:
    """attempts hits max → terminal 'failed' state."""
    session = _FakeSession()
    job_id = uuid.uuid4()
    src_id = uuid.uuid4()
    # attempts=4 in the queue + the tick's increment puts it at 5.
    session.queued_jobs = [{"id": job_id, "source_table": "ledger_events", "source_id": src_id, "attempts": 4}]
    session.source_rows["ledger_events"] = [{"id": src_id, "summary": "x"}]

    embedder = AsyncMock()
    embedder.embed.side_effect = VoyageError("permanent")

    report = await run_embedder_tick(session, embedder=embedder, max_attempts=5)

    assert report.failed == 1
    assert session.job_state[job_id]["status"] == "failed"
    assert "permanent" in (session.job_state[job_id]["last_error"] or "")


@pytest.mark.asyncio
async def test_tick_missing_source_row_fails_just_that_job() -> None:
    """One job's source row was deleted between enqueue and tick → mark only that
    job failed, other jobs in the batch still embed."""
    session = _FakeSession()
    job_ids = [uuid.uuid4() for _ in range(2)]
    src_ids = [uuid.uuid4() for _ in range(2)]
    session.queued_jobs = [
        {"id": job_ids[0], "source_table": "ledger_events", "source_id": src_ids[0], "attempts": 0},
        {"id": job_ids[1], "source_table": "ledger_events", "source_id": src_ids[1], "attempts": 0},
    ]
    # Only the first source row exists.
    session.source_rows["ledger_events"] = [{"id": src_ids[0], "summary": "ok"}]

    embedder = AsyncMock()
    embedder.embed.return_value = [[0.2] * VOYAGE_DIM]

    report = await run_embedder_tick(session, embedder=embedder)

    assert report.succeeded == 1
    assert report.failed == 1
    assert session.job_state[job_ids[0]]["status"] == "done"
    assert session.job_state[job_ids[1]]["status"] == "queued"  # retry path
    assert "not found" in (session.job_state[job_ids[1]]["last_error"] or "")


@pytest.mark.asyncio
async def test_tick_groups_by_source_table_one_voyage_call_per_group() -> None:
    """Two different tables in one tick → two Voyage calls (one per group)."""
    session = _FakeSession()
    j_ledger = uuid.uuid4()
    j_node = uuid.uuid4()
    s_ledger = uuid.uuid4()
    s_node = uuid.uuid4()
    session.queued_jobs = [
        {"id": j_ledger, "source_table": "ledger_events", "source_id": s_ledger, "attempts": 0},
        {"id": j_node, "source_table": "matrix_nodes", "source_id": s_node, "attempts": 0},
    ]
    session.source_rows["ledger_events"] = [{"id": s_ledger, "summary": "L"}]
    session.source_rows["matrix_nodes"] = [{"id": s_node, "title": "N", "description": "D"}]

    embedder = AsyncMock()
    embedder.embed.return_value = [[0.3] * VOYAGE_DIM]

    report = await run_embedder_tick(session, embedder=embedder)

    assert embedder.embed.await_count == 2
    assert report.succeeded == 2
    assert report.by_source_table == {"ledger_events": 1, "matrix_nodes": 1}


@pytest.mark.asyncio
async def test_tick_matrix_node_composes_title_and_description() -> None:
    session = _FakeSession()
    job_id = uuid.uuid4()
    src_id = uuid.uuid4()
    session.queued_jobs = [{"id": job_id, "source_table": "matrix_nodes", "source_id": src_id, "attempts": 0}]
    session.source_rows["matrix_nodes"] = [{"id": src_id, "title": "Sponsor", "description": "Executive lead for SSO"}]

    embedder = AsyncMock()
    embedder.embed.return_value = [[0.0] * VOYAGE_DIM]

    await run_embedder_tick(session, embedder=embedder)

    sent = embedder.embed.await_args.args[0][0]
    assert sent == "Sponsor — Executive lead for SSO"


@pytest.mark.asyncio
async def test_tick_oracle_turn_uses_content_field() -> None:
    session = _FakeSession()
    job_id = uuid.uuid4()
    src_id = uuid.uuid4()
    session.queued_jobs = [{"id": job_id, "source_table": "oracle_chat_turns", "source_id": src_id, "attempts": 0}]
    session.source_rows["oracle_chat_turns"] = [{"id": src_id, "content": "what changed last week?"}]

    embedder = AsyncMock()
    embedder.embed.return_value = [[0.0] * VOYAGE_DIM]

    await run_embedder_tick(session, embedder=embedder)

    sent = embedder.embed.await_args.args[0][0]
    assert sent == "what changed last week?"


def test_run_embedder_tick_rejects_invalid_args() -> None:
    """Argument validation guards against typos in the CLI invocation."""
    import asyncio

    session = _FakeSession()
    embedder = AsyncMock()

    with pytest.raises(ValueError):
        asyncio.run(run_embedder_tick(session, batch_size=0, embedder=embedder))
    with pytest.raises(ValueError):
        asyncio.run(run_embedder_tick(session, max_attempts=0, embedder=embedder))
