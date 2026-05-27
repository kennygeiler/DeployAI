"""Voyage-3 embedding backfill worker (v2 Phase 5.5 Wave B, scope-v2 §10.2).

Polls the ``embedding_jobs`` queue (defined by Wave A's migration), batches
up to 50 rows per Voyage-3 call, writes the resulting 1024-dim vectors back
to the source table's ``embedding`` column, and marks the jobs done. One
tick processes one batch and returns; the CLI in
``control_plane.cli.embedder`` drives the poll loop with a 2-second sleep.

Why a separate worker
---------------------
Embeddings are the **fallback** retrieval path (``docs/agent-kenny/ethos.md``).
We keep the embedder out of the request path so a transient Voyage outage
never blocks ingest or chat. The queue + worker pattern also lets us batch
across rows for cost — Voyage charges per call, so 50-row batches are
~50x cheaper than per-row.

Source-table field mapping
--------------------------
Each row in ``embedding_jobs`` references a source row. The text we hand to
Voyage depends on which source table it points at:

- ``ledger_events`` → ``summary`` (already constrained to 1-500 chars by
  the ``ledger_summary_len`` check).
- ``matrix_nodes`` → ``title || ' — ' || description``.
- ``oracle_chat_turns`` → ``content`` (one-row-per-turn schema; the
  scope's "user_message + Reply: assistant_message" framing assumes a
  paired-row schema we don't actually have, so we embed each turn's
  ``content`` directly).
- ``matrix_insights`` → ``title || ' — ' || body``.

All inputs are truncated to 8 000 chars **before** the API call. Voyage-3's
hard limit is ~32 k tokens; 8 k chars is a safe pre-trim that caps both cost
and the risk of hitting the model's context.

Failure mode
------------
Each job's processing is wrapped in a try/except. On any failure:
- attempts < max → status flipped back to ``queued`` for the next tick.
- attempts >= max → status flipped to ``failed`` with ``last_error`` set.
Never let one bad job crash the tick.
"""

from __future__ import annotations

import logging
import time
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.embeddings.voyage_client import (
    VOYAGE_DIM,
    VoyageEmbedder,
    VoyageError,
)
from control_plane.domain.embedding_jobs import EMBEDDING_SOURCE_TABLES

_log = logging.getLogger(__name__)

DEFAULT_BATCH_SIZE = 50
DEFAULT_MAX_ATTEMPTS = 5
TRUNCATION_CAP_CHARS = 8000

SUPPORTED_SOURCE_TABLES: frozenset[str] = frozenset(EMBEDDING_SOURCE_TABLES)


@dataclass
class EmbedderTickReport:
    """Outcome of a single ``run_embedder_tick`` call."""

    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    latency_ms: int = 0
    by_source_table: dict[str, int] = field(default_factory=dict)


async def run_embedder_tick(
    session: AsyncSession,
    *,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    embedder: VoyageEmbedder | None = None,
) -> EmbedderTickReport:
    """Drain up to ``batch_size`` queued jobs from ``embedding_jobs``.

    Concurrency: uses ``SELECT … FOR UPDATE SKIP LOCKED`` so multiple
    worker replicas can drain the same queue without stepping on each
    other's rows. The job row is locked for the duration of the tick;
    if the process crashes mid-tick the lock releases on transaction
    rollback and another worker will retry the job.
    """
    if batch_size <= 0:
        msg = "batch_size must be positive"
        raise ValueError(msg)
    if max_attempts <= 0:
        msg = "max_attempts must be positive"
        raise ValueError(msg)

    started_at = time.monotonic()
    report = EmbedderTickReport()
    client = embedder or VoyageEmbedder()

    jobs = await _claim_jobs(session, batch_size=batch_size, max_attempts=max_attempts)
    if not jobs:
        report.latency_ms = int((time.monotonic() - started_at) * 1000)
        return report

    # Group by source_table so each Voyage call is homogeneous (one SQL
    # per-table fetch, one batched API call, one per-table write-back).
    by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for job in jobs:
        by_table[job["source_table"]].append(job)

    for source_table, group in by_table.items():
        await _process_group(
            session,
            source_table=source_table,
            jobs=group,
            embedder=client,
            max_attempts=max_attempts,
            report=report,
        )

    report.latency_ms = int((time.monotonic() - started_at) * 1000)
    return report


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


async def _claim_jobs(
    session: AsyncSession,
    *,
    batch_size: int,
    max_attempts: int,
) -> list[dict[str, Any]]:
    """Lock up to ``batch_size`` queued jobs and flip them to ``running``.

    Returns a list of plain dicts (id, source_table, source_id, attempts)
    so callers don't need a SQLAlchemy model — Wave A defines the column
    set, we only consume it here.
    """
    select_stmt = text(
        """
        SELECT id, source_table, source_id, attempts
        FROM embedding_jobs
        WHERE status = 'queued' AND attempts < :max_attempts
        ORDER BY created_at
        LIMIT :batch
        FOR UPDATE SKIP LOCKED
        """
    )
    rows = (
        (
            await session.execute(
                select_stmt,
                {"max_attempts": max_attempts, "batch": batch_size},
            )
        )
        .mappings()
        .all()
    )
    if not rows:
        return []

    job_ids = [row["id"] for row in rows]
    # ``= ANY(:ids)`` with a Python list of UUIDs maps cleanly to a
    # Postgres ``uuid[]`` literal under asyncpg and psycopg alike.
    update_stmt = text(
        """
        UPDATE embedding_jobs
        SET status = 'running',
            attempts = attempts + 1,
            updated_at = now()
        WHERE id = ANY(:ids)
        """
    )
    await session.execute(update_stmt, {"ids": job_ids})
    await session.flush()

    return [
        {
            "id": row["id"],
            "source_table": row["source_table"],
            "source_id": row["source_id"],
            "attempts": (row["attempts"] or 0) + 1,
        }
        for row in rows
    ]


async def _process_group(
    session: AsyncSession,
    *,
    source_table: str,
    jobs: list[dict[str, Any]],
    embedder: VoyageEmbedder,
    max_attempts: int,
    report: EmbedderTickReport,
) -> None:
    """Fetch text, embed, write back for one ``source_table`` group."""
    if source_table not in SUPPORTED_SOURCE_TABLES:
        for job in jobs:
            await _mark_failure(
                session,
                job=job,
                reason=f"unsupported source_table: {source_table}",
                max_attempts=max_attempts,
                report=report,
            )
        return

    try:
        texts_by_source_id = await _fetch_texts(
            session, source_table=source_table, source_ids=[j["source_id"] for j in jobs]
        )
    except Exception as exc:  # broad: text-fetch SQL failure shouldn't crash tick
        _log.warning("embedder: text-fetch failed for %s: %s", source_table, exc)
        for job in jobs:
            await _mark_failure(
                session,
                job=job,
                reason=f"text fetch failed: {exc}",
                max_attempts=max_attempts,
                report=report,
            )
        return

    # Partition jobs by whether we found text for them. Missing-source jobs
    # fail immediately rather than embedding an empty string and corrupting
    # the index.
    embed_jobs: list[dict[str, Any]] = []
    embed_texts: list[str] = []
    for job in jobs:
        raw = texts_by_source_id.get(job["source_id"])
        if raw is None:
            await _mark_failure(
                session,
                job=job,
                reason="source row not found or text empty",
                max_attempts=max_attempts,
                report=report,
            )
            continue
        embed_jobs.append(job)
        embed_texts.append(_truncate(raw))

    if not embed_jobs:
        return

    try:
        vectors = await embedder.embed(embed_texts)
    except VoyageError as exc:
        _log.warning("embedder: Voyage call failed: %s", exc)
        for job in embed_jobs:
            await _mark_failure(
                session,
                job=job,
                reason=f"voyage error: {exc}",
                max_attempts=max_attempts,
                report=report,
            )
        return
    except Exception as exc:  # broad on purpose
        _log.exception("embedder: unexpected Voyage error: %s", exc)
        for job in embed_jobs:
            await _mark_failure(
                session,
                job=job,
                reason=f"unexpected: {exc}",
                max_attempts=max_attempts,
                report=report,
            )
        return

    if len(vectors) != len(embed_jobs):
        _log.warning(
            "embedder: vector count mismatch (got %s, expected %s)",
            len(vectors),
            len(embed_jobs),
        )
        for job in embed_jobs:
            await _mark_failure(
                session,
                job=job,
                reason="vector count mismatch",
                max_attempts=max_attempts,
                report=report,
            )
        return

    # Write vectors back + mark jobs done. Each write is its own statement
    # so one bad row (e.g. row deleted between fetch and write-back) only
    # fails that one job.
    for job, vector in zip(embed_jobs, vectors, strict=True):
        try:
            await _write_vector(
                session,
                source_table=source_table,
                source_id=job["source_id"],
                vector=vector,
            )
            await _mark_done(session, job_id=job["id"])
        except Exception as exc:  # broad: per-row write failure
            _log.warning(
                "embedder: write-back failed for %s id=%s: %s",
                source_table,
                job["source_id"],
                exc,
            )
            await _mark_failure(
                session,
                job=job,
                reason=f"write-back failed: {exc}",
                max_attempts=max_attempts,
                report=report,
            )
            continue
        report.processed += 1
        report.succeeded += 1
        report.by_source_table[source_table] = report.by_source_table.get(source_table, 0) + 1


def _truncate(raw: str) -> str:
    """Pre-trim to ``TRUNCATION_CAP_CHARS`` to bound cost + token usage."""
    if len(raw) <= TRUNCATION_CAP_CHARS:
        return raw
    return raw[:TRUNCATION_CAP_CHARS]


async def _fetch_texts(
    session: AsyncSession,
    *,
    source_table: str,
    source_ids: list[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """Pull the text to embed for each source row, indexed by source id."""
    if source_table == "ledger_events":
        stmt = text("SELECT id, summary FROM ledger_events WHERE id = ANY(:ids)")
    elif source_table == "matrix_nodes":
        stmt = text("SELECT id, title, description FROM matrix_nodes WHERE id = ANY(:ids)")
    elif source_table == "oracle_chat_turns":
        stmt = text("SELECT id, content FROM oracle_chat_turns WHERE id = ANY(:ids)")
    elif source_table == "matrix_insights":
        stmt = text("SELECT id, title, body FROM matrix_insights WHERE id = ANY(:ids)")
    else:  # pragma: no cover — guarded by SUPPORTED_SOURCE_TABLES upstream
        msg = f"unsupported source_table: {source_table}"
        raise ValueError(msg)

    rows = (await session.execute(stmt, {"ids": source_ids})).mappings().all()
    out: dict[uuid.UUID, str] = {}
    for row in rows:
        composed = _compose_text(source_table, row)
        if composed:
            out[row["id"]] = composed
    return out


def _compose_text(source_table: str, row: Any) -> str:
    if source_table == "ledger_events":
        return (row["summary"] or "").strip()
    if source_table == "matrix_nodes":
        title = (row["title"] or "").strip()
        description = (row["description"] or "").strip()
        if title and description:
            return f"{title} — {description}"
        return title or description
    if source_table == "oracle_chat_turns":
        return (row["content"] or "").strip()
    if source_table == "matrix_insights":
        title = (row["title"] or "").strip()
        body = (row["body"] or "").strip()
        if title and body:
            return f"{title} — {body}"
        return title or body
    return ""  # pragma: no cover


async def _write_vector(
    session: AsyncSession,
    *,
    source_table: str,
    source_id: uuid.UUID,
    vector: list[float],
) -> None:
    """``UPDATE {table} SET embedding = :vec WHERE id = :id``.

    Source table is whitelisted via ``SUPPORTED_SOURCE_TABLES`` so the
    f-string interpolation is safe — no path lets user input reach this
    branch.
    """
    if source_table not in SUPPORTED_SOURCE_TABLES:  # pragma: no cover
        msg = f"refusing to write to unknown table: {source_table}"
        raise ValueError(msg)
    if len(vector) != VOYAGE_DIM:
        msg = f"vector dim {len(vector)} != expected {VOYAGE_DIM}"
        raise ValueError(msg)
    literal = "[" + ",".join(repr(float(x)) for x in vector) + "]"
    stmt = text(f"UPDATE {source_table} SET embedding = CAST(:vec AS vector) WHERE id = :id")
    await session.execute(stmt, {"vec": literal, "id": source_id})


async def _mark_done(session: AsyncSession, *, job_id: uuid.UUID) -> None:
    await session.execute(
        text(
            """
            UPDATE embedding_jobs
            SET status = 'done', last_error = NULL, updated_at = now()
            WHERE id = :id
            """
        ),
        {"id": job_id},
    )


async def _mark_failure(
    session: AsyncSession,
    *,
    job: dict[str, Any],
    reason: str,
    max_attempts: int,
    report: EmbedderTickReport,
) -> None:
    """Failed → either back to queued (retry) or terminal failed state."""
    status = "failed" if job["attempts"] >= max_attempts else "queued"
    await session.execute(
        text(
            """
            UPDATE embedding_jobs
            SET status = :status,
                last_error = :reason,
                updated_at = now()
            WHERE id = :id
            """
        ),
        {"status": status, "reason": reason[:500], "id": job["id"]},
    )
    report.processed += 1
    report.failed += 1


__all__ = [
    "DEFAULT_BATCH_SIZE",
    "DEFAULT_MAX_ATTEMPTS",
    "SUPPORTED_SOURCE_TABLES",
    "TRUNCATION_CAP_CHARS",
    "EmbedderTickReport",
    "run_embedder_tick",
]
