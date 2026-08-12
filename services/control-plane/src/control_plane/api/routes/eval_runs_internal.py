"""Internal API — eval-run history (Wave 4 showcase, ticket G8).

``POST /internal/v1/admin/eval-runs`` records one execution of the
golden-question eval runner; ``GET`` lists recorded runs newest-first so
the admin dashboard can chart quality trends (pass rate, hallucination
rate, leaks) over time.

Ingest is deliberately liberal: the body is the runner's report JSON as-is
(``tests/golden/agent_kenny/runner.py`` writes it; ``--persist-url`` posts
it here). Whatever summary fields the report carries are lifted into typed
columns — under either their storage names (``question_count``,
``p50_ms``) or the runner's names (``total_questions``,
``latency_p50_ms``) — and the whole payload is stored verbatim in the
``report`` jsonb column. Missing counters default to zero; malformed
values are treated as missing rather than rejecting the run. The one hard
requirement is ``source`` ∈ {ci, local, longitudinal} (body field, or the
``source`` query param, defaulting to ``local``).

Platform-level ops data (no tenant): gated by :func:`require_internal`
(the global key), like the other admin/ops routes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.internal_auth import require_internal
from control_plane.db import get_app_db_session
from control_plane.domain.eval_runs import EVAL_RUN_SOURCES, EvalRun

router = APIRouter(prefix="/admin/eval-runs", tags=["internal-admin-eval-runs"])

_DEFAULT_LIMIT = 50
_MAX_LIMIT = 500


class EvalRunRead(BaseModel):
    """One recorded run — the typed summary columns, without the raw report.

    The ``report`` jsonb (which includes per-question results) stays out of
    the list payload on purpose: fifty full reports would dwarf the trend
    data the dashboard actually renders.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    run_at: datetime
    source: str
    runtime: str | None
    question_count: int
    pass_rate: float
    idk_rate: float
    hallucination_rate: float
    cross_engagement_leak_count: int
    p50_ms: float | None
    p95_ms: float | None


class EvalRunListResponse(BaseModel):
    runs: list[EvalRunRead]


def _as_float(value: Any) -> float | None:
    """Liberal float coercion: malformed values count as missing."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_int(value: Any) -> int | None:
    """Liberal int coercion: malformed values count as missing."""
    f = _as_float(value)
    return int(f) if f is not None else None


def _first(report: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in report:
            return report[key]
    return None


@router.post(
    "",
    response_model=EvalRunRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def record_eval_run(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    report: Annotated[dict[str, Any], Body()],
    source: Annotated[str | None, Query()] = None,
) -> EvalRunRead:
    """Record one eval-runner execution (report JSON in, summary row out)."""
    resolved_source = report.get("source") if isinstance(report.get("source"), str) else source
    resolved_source = (resolved_source or "local").strip().lower()
    if resolved_source not in EVAL_RUN_SOURCES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"source must be one of {list(EVAL_RUN_SOURCES)}",
        )

    runtime_raw = _first(report, "runtime", "agent_runtime")
    row = EvalRun(
        source=resolved_source,
        runtime=runtime_raw if isinstance(runtime_raw, str) else None,
        question_count=_as_int(_first(report, "question_count", "total_questions")) or 0,
        pass_rate=_as_float(report.get("pass_rate")) or 0.0,
        idk_rate=_as_float(report.get("idk_rate")) or 0.0,
        hallucination_rate=_as_float(report.get("hallucination_rate")) or 0.0,
        cross_engagement_leak_count=_as_int(report.get("cross_engagement_leak_count")) or 0,
        p50_ms=_as_float(_first(report, "p50_ms", "latency_p50_ms")),
        p95_ms=_as_float(_first(report, "p95_ms", "latency_p95_ms")),
        report=report,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return EvalRunRead.model_validate(row)


@router.get("", response_model=EvalRunListResponse, dependencies=[Depends(require_internal)])
async def list_eval_runs(
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    limit: Annotated[int, Query(ge=1, le=_MAX_LIMIT)] = _DEFAULT_LIMIT,
) -> EvalRunListResponse:
    """List recorded runs, newest first (``id`` breaks run_at ties stably)."""
    stmt = select(EvalRun).order_by(EvalRun.run_at.desc(), EvalRun.id.desc()).limit(limit)
    rows = list((await session.execute(stmt)).scalars().all())
    return EvalRunListResponse(runs=[EvalRunRead.model_validate(r) for r in rows])
