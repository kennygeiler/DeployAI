"""Longitudinal replay of the Agent Kenny eval (ticket G3, scope-v2 §11).

Replays the eval at several corpus horizons — e.g. an engagement that is
182, 730, and 1825 days old — and asserts retrieval quality does not
degrade as the corpus grows. Each checkpoint gets a truly fresh database
(schema dropped + re-migrated) and a progressive-prefix BlueState-XL seed
(``horizon_weeks``: same UUIDs as the full corpus, later events simply
absent).

The question subset is sampled ONCE, from the questions whose
``valid_from_week`` the EARLIEST checkpoint already covers, and replayed
identically at every checkpoint. Facts derived by G2 are monotone
(never-closed risks stay open, sponsors never depart), so a question valid
at the shortest horizon is valid at every longer one — and holding the
subset fixed is what makes pass_rate comparable across checkpoints: same
questions, growing haystack. A per-checkpoint resample would fold sample
composition into the degradation signal.

Degradation contract:

- exit 2 — any cross-engagement leak at any checkpoint (security gate).
- exit 3 — a checkpoint's pass_rate drops more than the tolerance
  (``--tolerance`` / env ``DEGRADATION_TOLERANCE``, default 0.10) below
  the best pass_rate of any earlier (shorter-horizon) checkpoint.
- exit 1 — harness/transport errors.

CLI::

    uv run python -m tests.golden.agent_kenny.longitudinal \\
        --checkpoints 182,365,730,1095,1825 --questions derived \\
        --per-checkpoint 12 --seed 0 --report /tmp/longitudinal.json

Run from ``services/control-plane``. Same environment contract as the
golden runner: no ``DATABASE_URL`` → throwaway pgvector testcontainer;
no LLM key → stub provider (offline, deterministic — the CI job pins
``DEPLOYAI_LLM_PROVIDER=stub``).
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import random
import uuid
from datetime import UTC, datetime
from pathlib import Path

from httpx import ASGITransport, AsyncClient

from .derive import derive_questions
from .runner import (
    _DEFAULT_REPORT_DIR,
    load_questions,
    provision_database,
    reset_database_schema,
    run_all,
)
from .types import CheckpointReport, LongitudinalReport, Question, RunReport

_log = logging.getLogger(__name__)

DEFAULT_CHECKPOINT_DAYS = (182, 365, 730, 1095, 1825)
DEFAULT_TOLERANCE = 0.10


def checkpoint_weeks(days: int, total_weeks: int) -> int:
    """Map a checkpoint horizon in days onto seedable whole weeks."""
    return max(1, min(total_weeks, days // 7))


def eligible_questions(questions: list[Question], horizon_weeks: int) -> list[Question]:
    """Questions whose facts exist by ``horizon_weeks``.

    A missing ``valid_from_week`` (the curated 30 predate the tag) is
    treated as week 1 — only the derived set carries real validity data,
    and it is the default question source here.
    """
    return [q for q in questions if (q.valid_from_week or 1) <= horizon_weeks]


def select_subset(questions: list[Question], *, seed: int, per_checkpoint: int) -> list[Question]:
    """Deterministic sample of the replay subset.

    Called once per run, over the questions eligible at the EARLIEST
    checkpoint; the same subset replays at every horizon (see module
    docstring for why). Seeded so the same ``--seed`` always picks the
    same questions.
    """
    ordered = sorted(questions, key=lambda q: q.id)
    if per_checkpoint >= len(ordered):
        return ordered
    rng = random.Random(f"longitudinal:{seed}")
    picked = rng.sample(ordered, per_checkpoint)
    return sorted(picked, key=lambda q: q.id)


def _citation_precision(run: RunReport) -> float | None:
    total = sum(r.expected_citation_ids_total for r in run.results)
    if total == 0:
        return None
    matched = sum(r.expected_citation_ids_matched for r in run.results)
    return matched / total


def assess_degradation(checkpoints: list[CheckpointReport], tolerance: float) -> tuple[bool, list[str]]:
    """Flag any checkpoint whose pass_rate fell more than ``tolerance``
    below the best earlier (shorter-horizon) checkpoint."""
    notes: list[str] = []
    degraded = False
    best_earlier: float | None = None
    for cp in checkpoints:
        if best_earlier is not None and cp.pass_rate < best_earlier - tolerance:
            degraded = True
            notes.append(
                f"checkpoint {cp.checkpoint_days}d: pass_rate {cp.pass_rate:.2f} dropped more than "
                f"{tolerance:.2f} below best earlier checkpoint ({best_earlier:.2f})"
            )
        best_earlier = cp.pass_rate if best_earlier is None else max(best_earlier, cp.pass_rate)
    return degraded, notes


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tests.golden.agent_kenny.longitudinal",
        description="Replay the Agent Kenny eval across corpus horizons and gate on degradation.",
    )
    parser.add_argument(
        "--checkpoints",
        type=str,
        default=",".join(str(d) for d in DEFAULT_CHECKPOINT_DAYS),
        metavar="D1,D2",
        help="comma-separated corpus ages in days (default 182,365,730,1095,1825)",
    )
    parser.add_argument(
        "--questions",
        type=str,
        default="derived",
        metavar="derived|PATH",
        help="'derived' (default) generates the G2 set in-process; otherwise a questions YAML path",
    )
    parser.add_argument(
        "--per-checkpoint",
        type=int,
        default=12,
        metavar="N",
        help="questions per checkpoint (deterministic sample; default 12)",
    )
    parser.add_argument("--seed", type=int, default=0, metavar="S", help="sampling seed (default 0)")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        metavar="PATH",
        help="report location (default eval-reports/agent-kenny-longitudinal-<ts>.json)",
    )
    parser.add_argument(
        "--tolerance",
        type=float,
        default=None,
        metavar="T",
        help="max allowed pass_rate drop vs the best earlier checkpoint "
        "(default: env DEGRADATION_TOLERANCE, else 0.10)",
    )
    parser.add_argument(
        "--seed-days",
        type=int,
        default=30,
        metavar="D",
        help="snapshot-backfill horizon per checkpoint (default 30 — snapshots are not under eval here)",
    )
    parser.add_argument(
        "--runtime",
        choices=("legacy", "langgraph"),
        default="legacy",
        help="agent runtime; exported as DEPLOYAI_AGENT_RUNTIME",
    )
    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    try:
        args.checkpoint_days = sorted({int(s.strip()) for s in args.checkpoints.split(",") if s.strip()})
    except ValueError:
        parser.error(f"--checkpoints must be a CSV of integers; got {args.checkpoints!r}")
    if not args.checkpoint_days or any(d < 7 for d in args.checkpoint_days):
        parser.error("--checkpoints needs at least one value >= 7 days")
    if args.per_checkpoint < 1:
        parser.error("--per-checkpoint must be >= 1")
    if args.tolerance is None:
        raw = os.environ.get("DEGRADATION_TOLERANCE", "").strip()
        args.tolerance = float(raw) if raw else DEFAULT_TOLERANCE
    if not 0 <= args.tolerance <= 1:
        parser.error("--tolerance must be within [0, 1]")
    return args


def _load_question_source(source: str) -> list[Question]:
    if source == "derived":
        return derive_questions()
    return load_questions(Path(source), enforce_distribution=False)


async def _run_checkpoint(
    *,
    db_url: str,
    checkpoint_days: int,
    horizon: int,
    subset: list[Question],
    eligible_count: int,
    seed_days: int,
) -> CheckpointReport:
    """Reset the schema, seed the horizon prefix, run the subset."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from control_plane.agents.agent_kenny.checkpointer import close_checkpointer
    from control_plane.db import clear_engine_cache
    from control_plane.main import app
    from control_plane.scenarios.bluestate_xl import ENGAGEMENT_ID as XL_ENGAGEMENT_ID
    from control_plane.scenarios.bluestate_xl import TENANT_ID as XL_TENANT_ID
    from control_plane.scenarios.bluestate_xl.runner import apply_bluestate_xl_scenario

    reset_database_schema(db_url)
    clear_engine_cache()

    tenant_id = uuid.UUID(XL_TENANT_ID)
    engagement_id = uuid.UUID(XL_ENGAGEMENT_ID)

    seed_engine = create_async_engine(db_url)
    try:
        session_factory = async_sessionmaker(seed_engine, expire_on_commit=False)
        async with session_factory() as session:
            summary = await apply_bluestate_xl_scenario(
                session,
                tenant_id=tenant_id,
                days=seed_days,
                horizon_weeks=horizon,
            )
            await session.commit()
        print(
            f"[checkpoint {checkpoint_days}d] seeded horizon_weeks={horizon}: "
            f"{summary.ledger_event_count} ledger events, {summary.risk_count} risks, "
            f"{summary.matrix_edge_count} edges"
        )
    finally:
        await seed_engine.dispose()

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=120.0)
    client.headers["X-DeployAI-Internal-Key"] = os.environ["DEPLOYAI_INTERNAL_API_KEY"]
    try:
        run = await run_all(
            client=client,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            write_report=False,
            questions=subset,
        )
    finally:
        await client.aclose()
        await close_checkpointer()
        clear_engine_cache()

    return CheckpointReport(
        checkpoint_days=checkpoint_days,
        horizon_weeks=horizon,
        eligible_questions=eligible_count,
        questions_run=len(subset),
        question_ids=[q.id for q in subset],
        pass_rate=run.pass_rate,
        citation_precision=_citation_precision(run),
        latency_p50_ms=run.latency_p50_ms,
        latency_p95_ms=run.latency_p95_ms,
        cross_engagement_leak_count=run.cross_engagement_leak_count,
        run=run,
    )


async def _amain(args: argparse.Namespace) -> LongitudinalReport:
    os.environ["DEPLOYAI_AGENT_KENNY_V2_ENABLED"] = "1"
    os.environ["DEPLOYAI_AGENT_RUNTIME"] = args.runtime
    os.environ.setdefault("DEPLOYAI_INTERNAL_API_KEY", "agent-kenny-longitudinal-cli")

    from control_plane.scenarios.bluestate_xl.events import TOTAL_WEEKS

    questions = _load_question_source(args.questions)
    started_at = datetime.now(UTC)

    # One fixed subset, drawn from what the SHORTEST horizon already
    # knows, replayed at every checkpoint (module docstring).
    min_horizon = checkpoint_weeks(min(args.checkpoint_days), TOTAL_WEEKS)
    common_pool = eligible_questions(questions, min_horizon)
    if not common_pool:
        raise RuntimeError(f"no questions are valid by week {min_horizon}; widen --checkpoints or the question set")
    subset = select_subset(common_pool, seed=args.seed, per_checkpoint=args.per_checkpoint)
    print(f"replay subset ({len(subset)} of {len(common_pool)} valid by week {min_horizon}): {[q.id for q in subset]}")

    db_url, container = provision_database()
    checkpoints: list[CheckpointReport] = []
    try:
        os.environ["DATABASE_URL"] = db_url
        for days in args.checkpoint_days:
            horizon = checkpoint_weeks(days, TOTAL_WEEKS)
            eligible = eligible_questions(questions, horizon)
            checkpoints.append(
                await _run_checkpoint(
                    db_url=db_url,
                    checkpoint_days=days,
                    horizon=horizon,
                    subset=subset,
                    eligible_count=len(eligible),
                    seed_days=args.seed_days,
                )
            )
    finally:
        if container is not None:
            container.stop()

    degraded, notes = assess_degradation(checkpoints, args.tolerance)
    return LongitudinalReport(
        started_at=started_at,
        finished_at=datetime.now(UTC),
        seed=args.seed,
        per_checkpoint=args.per_checkpoint,
        tolerance=args.tolerance,
        questions_source=args.questions,
        checkpoints=checkpoints,
        total_leaks=sum(cp.cross_engagement_leak_count for cp in checkpoints),
        degraded=degraded,
        degradation_notes=notes,
    )


def _print_summary(report: LongitudinalReport, report_path: Path) -> None:
    print(f"\n=== Agent Kenny longitudinal report ({report_path}) ===")
    print(f"tolerance: {report.tolerance:.2f}  seed: {report.seed}  source: {report.questions_source}")
    for cp in report.checkpoints:
        precision = "n/a" if cp.citation_precision is None else f"{cp.citation_precision:.2f}"
        print(
            f"  {cp.checkpoint_days:>5}d (W{cp.horizon_weeks:>3}): "
            f"pass_rate={cp.pass_rate:.2f} citation_precision={precision} "
            f"p50={cp.latency_p50_ms}ms p95={cp.latency_p95_ms}ms "
            f"leaks={cp.cross_engagement_leak_count} "
            f"({cp.questions_run}/{cp.eligible_questions} eligible)"
        )
    print(f"total_leaks: {report.total_leaks}")
    print(f"degraded: {report.degraded}")
    for note in report.degradation_notes:
        print(f"  ! {note}")


def main(argv: list[str] | None = None) -> int:
    """Exit codes: 0 clean; 1 harness/transport error; 2 cross-engagement
    leak; 3 pass_rate degradation beyond tolerance."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    report = asyncio.run(_amain(args))

    report_path: Path | None = args.report
    if report_path is None:
        ts = report.started_at.strftime("%Y%m%dT%H%M%SZ")
        report_path = _DEFAULT_REPORT_DIR / f"agent-kenny-longitudinal-{ts}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    _print_summary(report, report_path)

    if report.total_leaks > 0:
        return 2
    if report.degraded:
        return 3
    if any(r.error for cp in report.checkpoints for r in cp.run.results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "DEFAULT_CHECKPOINT_DAYS",
    "DEFAULT_TOLERANCE",
    "assess_degradation",
    "build_arg_parser",
    "checkpoint_weeks",
    "eligible_questions",
    "main",
    "select_subset",
]
