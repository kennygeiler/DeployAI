"""ORM for longitudinal eval-run history (Wave 4 showcase, ticket G8).

One row per execution of the golden-question eval runner
(``tests/golden/agent_kenny/runner.py``). Summary metrics live in typed
columns so trend queries stay cheap; the runner's whole report JSON is
stored verbatim in ``report`` for drill-down.

Platform-level by design: NO ``tenant_id`` — eval runs measure the
product against synthetic fixtures, not tenant data. The table is
documented in the RLS catalog test's exemption list
(``tests/integration/test_rls_expansion.py``) and gated at the route
layer by the global internal key (``require_internal``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, Double, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base

EVAL_RUN_SOURCES: tuple[str, ...] = ("ci", "local", "longitudinal")


class EvalRun(Base):
    """One recorded eval-runner execution (append-only)."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    run_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    source: Mapped[str] = mapped_column(Text(), nullable=False)
    runtime: Mapped[str | None] = mapped_column(Text(), nullable=True)
    question_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    pass_rate: Mapped[float] = mapped_column(Double(), nullable=False)
    idk_rate: Mapped[float] = mapped_column(Double(), nullable=False)
    hallucination_rate: Mapped[float] = mapped_column(Double(), nullable=False)
    cross_engagement_leak_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    p50_ms: Mapped[float | None] = mapped_column(Double(), nullable=True)
    p95_ms: Mapped[float | None] = mapped_column(Double(), nullable=True)
    report: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        server_default=text("'{}'::jsonb"),
    )

    __table_args__ = (
        CheckConstraint(
            "source IN ('ci','local','longitudinal')",
            name="ck_eval_runs_source",
        ),
        Index("ix_eval_runs_run_at", text("run_at DESC")),
    )


__all__ = ["EVAL_RUN_SOURCES", "EvalRun"]
