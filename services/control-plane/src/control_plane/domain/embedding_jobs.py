"""ORM + Pydantic shapes for the ``embedding_jobs`` queue (Phase 5.5 Wave A).

The queue is populated by the ``deployai_enqueue_embedding_job`` trigger
attached to every embedding-enabled source table (see migration
``20260613_0050_pgvector_embeddings.py``). The embedder worker shipped by
Wave B polls ``status = 'queued'`` ordered by ``created_at``, batches up
to 50 rows per Voyage-3 call, writes the resulting vectors back to the
source row's ``embedding`` column, and flips the job to ``done``.

This module ships only the SQLAlchemy mapping and the read-shape
Pydantic model. The worker itself, retry policy, and any management
routes are out-of-scope for Wave A (they land with the worker in Wave B).

See ``docs/agent-kenny/scope-v2.md`` §10 (Phase 5.5).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict
from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base

# Catalogs — single source of truth, mirrored against the CHECK
# constraints in migration 0050. Import these from worker code rather
# than re-declaring magic strings.
EMBEDDING_SOURCE_TABLES: tuple[str, ...] = (
    "ledger_events",
    "matrix_nodes",
    "oracle_chat_turns",
    "matrix_insights",
)

EMBEDDING_JOB_STATUSES: tuple[str, ...] = ("queued", "running", "done", "failed")

EmbeddingSourceTable = Literal[
    "ledger_events",
    "matrix_nodes",
    "oracle_chat_turns",
    "matrix_insights",
]

EmbeddingJobStatus = Literal["queued", "running", "done", "failed"]


class EmbeddingJob(Base):
    """One pending or completed embedding job for a single source row.

    The unique ``(source_table, source_id)`` constraint guarantees one
    row per source — UPDATEs on the source table that fire the enqueue
    trigger bump the existing job back to ``queued`` rather than piling
    up duplicates (handled by the trigger's ``ON CONFLICT DO UPDATE``).
    """

    __tablename__ = "embedding_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    source_table: Mapped[str] = mapped_column(Text(), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(
        Text(),
        nullable=False,
        server_default=text("'queued'"),
    )
    attempts: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        server_default=text("0"),
    )
    last_error: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "source_table IN (" + ", ".join(f"'{t}'" for t in EMBEDDING_SOURCE_TABLES) + ")",
            name="ck_embedding_jobs_source_table",
        ),
        CheckConstraint(
            "status IN (" + ", ".join(f"'{s}'" for s in EMBEDDING_JOB_STATUSES) + ")",
            name="ck_embedding_jobs_status",
        ),
        UniqueConstraint(
            "source_table",
            "source_id",
            name="uq_embedding_jobs_source",
        ),
        Index(
            "idx_embedding_jobs_status_created_at",
            "status",
            "created_at",
        ),
    )


class EmbeddingJobRead(BaseModel):
    """Read-shape for the worker / admin routes (Wave B+).

    Wave A exposes the type for symmetry with sibling ORMs in this tree;
    no route consumes it yet.
    """

    model_config = ConfigDict(extra="forbid")

    id: uuid.UUID
    tenant_id: uuid.UUID
    source_table: EmbeddingSourceTable
    source_id: uuid.UUID
    status: EmbeddingJobStatus
    attempts: int
    last_error: str | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_orm_row(cls, row: EmbeddingJob) -> EmbeddingJobRead:
        # ``source_table`` + ``status`` are typed as ``str`` on the ORM but
        # the column CHECKs constrain them to the Literal alphabets above.
        # Pydantic v2 narrows the str to the Literal at validation time, so
        # no explicit cast is needed here.
        return cls(
            id=row.id,
            tenant_id=row.tenant_id,
            source_table=row.source_table,
            source_id=row.source_id,
            status=row.status,
            attempts=row.attempts,
            last_error=row.last_error,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )


__all__ = [
    "EMBEDDING_JOB_STATUSES",
    "EMBEDDING_SOURCE_TABLES",
    "EmbeddingJob",
    "EmbeddingJobRead",
    "EmbeddingJobStatus",
    "EmbeddingSourceTable",
]
