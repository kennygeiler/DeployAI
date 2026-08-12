"""Agent Kenny v2 golden-question runner (scope-v2 §11.2, tickets G1/G4/G5).

Drives the ``/internal/v1/engagements/{eid}/oracle/chat/stream-v2``
endpoint against a freshly-seeded BlueState-XL fixture, parses the SSE
frame stream, and emits per-question metrics + an aggregate report.

Public surface — three callables, the CLI entry point, and the Pydantic
models in :mod:`types`. Everything else is intentionally underscored.

Hard constraints:

- 30 questions hard count.
- BlueState-XL fixture seed reused — never re-seeded inline.

CLI (ticket G1)::

    uv run python -m tests.golden.agent_kenny.runner \\
        --limit 5 --random --seed 7 --report /tmp/eval-report.json

Run from ``services/control-plane``. With no ``DATABASE_URL`` in the
environment the CLI starts the same pgvector testcontainer the
integration conftest uses, migrates it, seeds BlueState-XL, and drives
the FastAPI app in-process over ``ASGITransport``. With no LLM API key
the app resolves the stub provider, so the run completes offline —
that is the deterministic path the PR gate in ``ci.yml`` relies on.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import random
import re
import time
import uuid
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml
from httpx import AsyncClient

from .types import (
    CATEGORIES,
    EXPECTED_DISTRIBUTION,
    CategoryDistribution,
    Question,
    QuestionResult,
    RunReport,
)

_log = logging.getLogger(__name__)

# scope-v2 §11.1 — YAML location is fixed by the spec.
QUESTIONS_PATH: Path = Path(__file__).resolve().parent / "questions.yaml"

# Default report directory; configurable per-call via ``run_all(..., report_dir=...)``.
_DEFAULT_REPORT_DIR: Path = Path(__file__).resolve().parents[4] / "eval-reports"

# Detected via simple regex over the final reply text. We don't run the LLM
# judge here unless ``EVAL_LLM_JUDGE=1`` (see ``_llm_judge_match``).
_IDK_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bi (?:don'?t|do not) know\b", re.IGNORECASE),
    re.compile(r"\bi (?:can'?t|cannot) (?:answer|find|locate|determine)\b", re.IGNORECASE),
    re.compile(r"\bunable to (?:answer|find|determine|locate)\b", re.IGNORECASE),
    re.compile(r"\bno (?:matching|relevant) (?:data|records|evidence|information)\b", re.IGNORECASE),
    re.compile(r"\bnot (?:in|available in) (?:the|this) (?:data|engagement|ledger)\b", re.IGNORECASE),
    re.compile(r"\bi'?m unable to answer\b", re.IGNORECASE),
    re.compile(r"\bno (?:information|data|evidence) (?:about|on|for)\b", re.IGNORECASE),
    re.compile(r"\binsufficient (?:data|evidence|information)\b", re.IGNORECASE),
    # The agent service substitutes "(no response)" when the model produced
    # zero visible text (service.py). A contentless reply is a non-answer,
    # same as the empty string _detect_idk already treats as IDK — this is
    # also what makes stub-provider runs deterministic for the PR gate.
    re.compile(r"^\s*\(no response\)\s*$"),
)


# --- YAML loading -------------------------------------------------------------


def load_questions(path: Path | None = None, *, enforce_distribution: bool = True) -> list[Question]:
    """Load + validate every entry in a questions YAML file.

    Validates that:

    1. The file parses as a YAML sequence.
    2. Each entry parses as a :class:`Question` (Pydantic enforces the
       schema — closed category enum, no extra fields).
    3. With ``enforce_distribution=True`` (the default, and always the
       right choice for the curated ``questions.yaml``), the count and
       per-category distribution match :data:`EXPECTED_DISTRIBUTION`
       exactly. The CLI's ``--questions PATH`` (e.g. the G2 derived set)
       passes ``False`` — schema validation and the duplicate-id check
       still apply.
    """
    src = path or QUESTIONS_PATH
    raw = yaml.safe_load(src.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{src} must be a YAML sequence; got {type(raw).__name__}")
    questions = [Question.model_validate(entry) for entry in raw]
    if enforce_distribution:
        _assert_distribution(questions)
    else:
        _assert_unique_ids(questions)
    return questions


def _assert_distribution(questions: list[Question]) -> None:
    """Hard-fail if the YAML drifts from the 30/8/8/6/4/4 split."""
    total = len(questions)
    expected_total = sum(EXPECTED_DISTRIBUTION.values())
    if total != expected_total:
        raise ValueError(f"expected {expected_total} questions; got {total}")
    counts: dict[str, int] = dict.fromkeys(EXPECTED_DISTRIBUTION, 0)
    for q in questions:
        if q.category not in counts:
            raise ValueError(f"category {q.category!r} not allowed in the curated set (question {q.id})")
        counts[q.category] += 1
    for cat, want in EXPECTED_DISTRIBUTION.items():
        if counts[cat] != want:
            raise ValueError(f"category {cat!r}: expected {want} questions, got {counts[cat]}")
    _assert_unique_ids(questions)


def _assert_unique_ids(questions: list[Question]) -> None:
    ids = [q.id for q in questions]
    if len(set(ids)) != len(ids):
        dupes = sorted({i for i in ids if ids.count(i) > 1})
        raise ValueError(f"duplicate question ids: {dupes}")


# --- SSE parsing --------------------------------------------------------------


@dataclass(frozen=True)
class _Frame:
    event: str
    data: Mapping[str, Any]


def _parse_sse_stream(payload: str) -> list[_Frame]:
    """Split an ``event:/data:\\n\\n`` SSE payload into parsed frames."""
    out: list[_Frame] = []
    for block in payload.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = ""
        data_text = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                data_text = line[len("data: ") :].strip()
        if not event_name:
            continue
        try:
            data = json.loads(data_text) if data_text else {}
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict):
            continue
        out.append(_Frame(event=event_name, data=data))
    return out


# --- Question execution -------------------------------------------------------


async def run_question(
    client: AsyncClient,
    question: Question,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    *,
    actor_user_id: uuid.UUID | None = None,
    conversation_id: uuid.UUID | None = None,
    request_timeout_s: float = 90.0,
) -> QuestionResult:
    """Drive ONE golden question through Agent Kenny.

    Posts to the stream-v2 endpoint, parses the SSE frames, classifies the
    response against the question's expectations, and returns a
    :class:`QuestionResult`.

    On transport error (non-2xx, network failure, malformed stream) the
    result still serialises cleanly — ``error`` carries the message and
    every numeric metric is zero. The caller is free to skip those when
    computing pass-rate.
    """
    actor = actor_user_id or uuid.UUID("aaaaaaa1-1111-4111-8111-111111111111")
    headers = {"X-DeployAI-Actor-Id": str(actor)}
    body = {
        "conversation_id": str(conversation_id) if conversation_id is not None else None,
        "message": question.question,
    }

    started = time.perf_counter()
    try:
        resp = await asyncio.wait_for(
            client.post(
                f"/internal/v1/engagements/{engagement_id}/oracle/chat/stream-v2",
                params={"tenant_id": str(tenant_id)},
                json=body,
                headers=headers,
            ),
            timeout=request_timeout_s,
        )
    except TimeoutError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return _empty_result(question, elapsed_ms=elapsed, error=f"timeout: {exc}")
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return _empty_result(question, elapsed_ms=elapsed, error=str(exc)[:200])
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    if resp.status_code != 200:
        return _empty_result(question, elapsed_ms=elapsed_ms, error=f"status_{resp.status_code}")

    frames = _parse_sse_stream(resp.text)
    return _classify_frames(question, frames, latency_ms=elapsed_ms)


def _empty_result(question: Question, *, elapsed_ms: int, error: str) -> QuestionResult:
    """Build a clean-shape failure result so callers can keep aggregating."""
    return QuestionResult(
        id=question.id,
        category=question.category,
        latency_ms=elapsed_ms,
        tool_calls=0,
        citations_total=0,
        citations_verified=0,
        citations_unverified=0,
        citations_external=0,
        revisions=0,
        adversarial_concerns=0,
        idk=question.should_idk,  # default: assume worst — if Kenny refused via error, treat as IDK-ish
        final_text="",
        expected_pass=question.should_idk,  # an empty answer "passes" only for IDK questions
        expected_kind_match=not question.expected_kinds,
        cross_engagement_leak=False,
        error=error,
        substring_pass=question.should_idk,
        judged_pass=None,
        is_negative_control=question.is_negative_control,
        expected_citation_ids_total=len(question.expected_citation_ids),
        expected_citation_ids_matched=0,
    )


def _classify_frames(question: Question, frames: list[_Frame], *, latency_ms: int) -> QuestionResult:
    """Walk one SSE frame stream and compute the per-question metrics."""
    tool_calls = sum(1 for f in frames if f.event == "tool_call")
    citations_verified = sum(1 for f in frames if f.event == "citation_verified")
    citations_unverified = sum(1 for f in frames if f.event == "citation_unverified")
    citations_external = sum(1 for f in frames if f.event == "citation_external")
    leaks = [f for f in frames if f.event == "cross_engagement_leak"]
    cross_engagement_leak = bool(leaks)
    adversarial = sum(1 for f in frames if f.event == "adversarial_concern")
    done = next((f for f in frames if f.event == "done"), None)

    final_text: str = ""
    revisions: int = 0
    if done is not None:
        final_text = str(done.data.get("final_text", ""))
        try:
            revisions = int(done.data.get("revision_attempts", 0) or 0)
        except (TypeError, ValueError):
            revisions = 0

    citation_kinds_seen: set[str] = set()
    citation_ids_seen: set[str] = set()
    for f in frames:
        if f.event in ("citation_verified", "citation_unverified", "citation_external"):
            kind = f.data.get("kind")
            if isinstance(kind, str):
                citation_kinds_seen.add(kind)
            identifier = f.data.get("id")
            if isinstance(identifier, str):
                citation_ids_seen.add(identifier.strip().lower())

    citations_total = citations_verified + citations_unverified + citations_external
    idk = _detect_idk(final_text)
    substring_pass = _expected_pass(question, final_text=final_text, idk=idk, leak=cross_engagement_leak)
    # Ticket G4 — second-tier LLM judge. Substring pre-filter first: the
    # judge only runs when the cheap check failed on a factual question
    # with a non-empty reply. ``_llm_judge_match`` itself gates on
    # EVAL_LLM_JUDGE=1 and silently skips on the stub provider.
    judged_pass: bool | None = None
    if not substring_pass and not question.should_idk and final_text:
        judged_pass = _llm_judge_match(question, final_text)
        if judged_pass is True and idk:
            # The judge cannot overrule a detected refusal on a factual
            # question — an IDK reply is a fail regardless of semantics.
            judged_pass = False
    expected_pass = substring_pass or judged_pass is True
    expected_kind_match = _expected_kind_match(question, citation_kinds_seen)

    # Ticket G2 — citation-id ground truth for derived questions. Every
    # expected id is a real seeded UUID (ledger event / node / insight);
    # count how many the reply actually cited, any citation frame kind.
    expected_ids = {i.strip().lower() for i in question.expected_citation_ids}
    matched_ids = len(expected_ids & citation_ids_seen)

    return QuestionResult(
        id=question.id,
        category=question.category,
        latency_ms=latency_ms,
        tool_calls=tool_calls,
        citations_total=citations_total,
        citations_verified=citations_verified,
        citations_unverified=citations_unverified,
        citations_external=citations_external,
        revisions=revisions,
        adversarial_concerns=adversarial,
        idk=idk,
        final_text=final_text,
        expected_pass=expected_pass,
        expected_kind_match=expected_kind_match,
        cross_engagement_leak=cross_engagement_leak,
        error=None,
        substring_pass=substring_pass,
        judged_pass=judged_pass,
        is_negative_control=question.is_negative_control,
        expected_citation_ids_total=len(expected_ids),
        expected_citation_ids_matched=matched_ids,
    )


def _detect_idk(final_text: str) -> bool:
    if not final_text:
        return True
    return any(p.search(final_text) for p in _IDK_PATTERNS)


def _expected_pass(question: Question, *, final_text: str, idk: bool, leak: bool) -> bool:
    """Pass/fail logic, by category:

    - ``negative`` + ``cross_engagement``: pass iff Kenny refused / said IDK.
      A cross-engagement leak ALSO counts as a pass for the cross_engagement
      category because the leak was caught (the security gate stripped the
      reply); the leak itself fails harder elsewhere (the aggregate report
      surfaces ``cross_engagement_leak_count`` as a top-line metric).
    - Everything else: substring-match every required term (case-insensitive)
      AND not IDK.
    """
    if question.should_idk:
        if question.category == "cross_engagement":
            return idk or leak
        return idk and not leak
    if not final_text:
        return False
    haystack = final_text.lower()
    for needle in question.expected_answer_contains:
        if needle.lower() not in haystack:
            return False
    return not idk


def _expected_kind_match(question: Question, kinds_seen: set[str]) -> bool:
    """Every expected kind must be present at least once in the citation stream.

    For IDK / negative questions there are no expected kinds and the check
    is trivially true (empty intersection requirement).
    """
    if not question.expected_kinds:
        return True
    expected = {k for k in question.expected_kinds}
    return expected.issubset(kinds_seen)


# --- Optional LLM judge (gated; default off) ----------------------------------


def _llm_judge_match(question: Question, final_text: str) -> bool | None:
    """Optional semantic-match check via the configured LLM provider.

    Off by default. Enable by setting ``EVAL_LLM_JUDGE=1``. Returns:

    - ``True`` / ``False`` when the judge ran successfully.
    - ``None`` when the judge is disabled, the provider isn't available,
      or the resolved provider is the stub (a stub "verdict" would be
      noise, so it is skipped silently — ticket G4).

    ``_classify_frames`` calls this as the second tier behind the cheap
    substring pre-filter: only substring FAILURES on factual questions
    reach the judge, so a passing run costs zero LLM calls.
    """
    if os.environ.get("EVAL_LLM_JUDGE", "").strip() not in ("1", "true", "yes", "on"):
        return None
    if question.should_idk:
        return None
    if not question.expected_answer_contains or not final_text:
        return None
    try:
        from control_plane.agents.llm import get_llm_provider
    except Exception:
        return None
    try:
        provider = get_llm_provider()
    except Exception:
        return None
    if str(getattr(provider, "id", "")).startswith("stub"):
        return None
    needles = "; ".join(question.expected_answer_contains)
    prompt = (
        "You are a strict eval judge. Reply with a single word: YES or NO.\n"
        f"Does the following response semantically contain ALL of: {needles}\n"
        f"---\n{final_text}\n---"
    )
    try:
        reply = provider.chat_complete(
            [{"role": "user", "content": prompt}],
            temperature=0.0,
            max_output_tokens=8,
        )
    except Exception:
        return None
    return bool(reply.strip().upper().startswith("YES"))


# --- Aggregation + report -----------------------------------------------------


async def run_all(
    question_ids: list[str] | None = None,
    *,
    client: AsyncClient | None = None,
    tenant_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
    actor_user_id: uuid.UUID | None = None,
    seed_fn: Any = None,
    seed_days: int = 365,
    report_dir: Path | None = None,
    write_report: bool = True,
    questions: list[Question] | None = None,
) -> RunReport:
    """Seed BlueState-XL fresh, run every question (or a subset), aggregate.

    ``client`` MUST be supplied by the caller — the runner does not own
    the ASGI transport / DB engine wiring; the integration test and the
    CLI (``main`` below) construct the ``AsyncClient`` against either a
    real CP deployment or the FastAPI app via ``ASGITransport``.

    ``questions`` overrides YAML loading with a pre-selected list (the
    CLI uses this for ``--limit/--random`` sampling). ``question_ids``
    filters the loaded set by id; passing both is rejected.

    ``seed_fn`` defaults to
    :func:`control_plane.scenarios.bluestate_xl.runner.apply_bluestate_xl_scenario`
    — pass an explicit callable from the test fixture when the seed needs
    a session the runner cannot construct (the common case).

    Returns the :class:`RunReport`. When ``write_report=True`` (default)
    also writes the JSON payload to ``eval-reports/agent-kenny-{ts}.json``.
    """
    if client is None:
        raise ValueError("run_all requires an httpx.AsyncClient; the harness does not own transport wiring")
    if questions is not None and question_ids is not None:
        raise ValueError("pass either questions or question_ids, not both")
    if questions is None:
        questions = load_questions()
        if question_ids is not None:
            wanted = set(question_ids)
            questions = [q for q in questions if q.id in wanted]
            if not questions:
                raise ValueError(f"no questions matched ids={question_ids}")
    elif not questions:
        raise ValueError("questions list is empty")

    effective_tenant = tenant_id or _default_tenant_id()
    effective_engagement = engagement_id or _default_engagement_id()

    if seed_fn is not None:
        # The test fixture passes a partially-applied callable
        # ``functools.partial(apply_bluestate_xl_scenario, session, days=...)``
        # so the runner doesn't need to know about DB sessions.
        result = seed_fn(tenant_id=effective_tenant, days=seed_days) if _accepts_kwargs(seed_fn) else seed_fn()
        if asyncio.iscoroutine(result):
            await result

    started_at = datetime.now(UTC)
    results: list[QuestionResult] = []
    for q in questions:
        r = await run_question(
            client,
            q,
            effective_tenant,
            effective_engagement,
            actor_user_id=actor_user_id,
        )
        results.append(r)
    finished_at = datetime.now(UTC)

    report = _aggregate(results, started_at=started_at, finished_at=finished_at)

    if write_report and results:
        out_dir = report_dir or _DEFAULT_REPORT_DIR
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = started_at.strftime("%Y%m%dT%H%M%SZ")
        out_path = out_dir / f"agent-kenny-{ts}.json"
        out_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        _log.info("wrote eval report %s", out_path)

    return report


def _accepts_kwargs(fn: Any) -> bool:
    """Best-effort check for whether ``seed_fn`` takes kwargs from the runner."""
    try:
        import inspect

        sig = inspect.signature(fn)
        return any(
            p.kind in (p.KEYWORD_ONLY, p.POSITIONAL_OR_KEYWORD, p.VAR_KEYWORD) and p.name in ("tenant_id", "days")
            for p in sig.parameters.values()
        )
    except (TypeError, ValueError):
        return False


def _aggregate(results: list[QuestionResult], *, started_at: datetime, finished_at: datetime) -> RunReport:
    total = len(results)
    if total == 0:
        return RunReport(
            started_at=started_at,
            finished_at=finished_at,
            total_questions=0,
            pass_rate=0.0,
            idk_rate=0.0,
            hallucination_rate=0.0,
            cross_engagement_leak_count=0,
            latency_p50_ms=0,
            latency_p95_ms=0,
            latency_p99_ms=0,
            by_category=[],
            results=[],
        )

    passes = sum(1 for r in results if r.expected_pass)
    idk = sum(1 for r in results if r.idk)
    citations_total = sum(r.citations_total for r in results)
    unverified = sum(r.citations_unverified for r in results)
    # Ticket G4 — honest hallucination denominator. A factual reply with
    # ZERO citations is fully unverified, not perfectly clean: each such
    # answer contributes one phantom unverified citation to both sides of
    # the ratio (a single zero-citation factual answer scores 1.0).
    # Exemptions: declines (idk), empty replies, and negative controls,
    # where a citation-free decline is the correct outcome.
    uncited_factual = sum(
        1 for r in results if r.citations_total == 0 and r.final_text and not r.idk and not r.is_negative_control
    )
    denominator = citations_total + uncited_factual
    hallucination_rate = ((unverified + uncited_factual) / denominator) if denominator else 0.0
    leaks = sum(1 for r in results if r.cross_engagement_leak)

    latencies = sorted(r.latency_ms for r in results)

    by_category: list[CategoryDistribution] = []
    for cat in CATEGORIES:
        subset = [r for r in results if r.category == cat]
        if not subset:
            continue
        sub_passes = sum(1 for r in subset if r.expected_pass)
        sub_idk = sum(1 for r in subset if r.idk)
        sub_leaks = sum(1 for r in subset if r.cross_engagement_leak)
        by_category.append(
            CategoryDistribution(
                category=cat,
                total=len(subset),
                passes=sub_passes,
                idk=sub_idk,
                leaks=sub_leaks,
                pass_rate=sub_passes / len(subset),
            )
        )

    return RunReport(
        started_at=started_at,
        finished_at=finished_at,
        total_questions=total,
        pass_rate=passes / total,
        idk_rate=idk / total,
        hallucination_rate=hallucination_rate,
        cross_engagement_leak_count=leaks,
        latency_p50_ms=_pct(latencies, 50),
        latency_p95_ms=_pct(latencies, 95),
        latency_p99_ms=_pct(latencies, 99),
        by_category=by_category,
        results=results,
    )


def _pct(sorted_values: list[int], pct: int) -> int:
    if not sorted_values:
        return 0
    # Nearest-rank percentile (good enough for N=30, no scipy dep).
    k = max(0, min(len(sorted_values) - 1, (pct * len(sorted_values)) // 100))
    return sorted_values[k]


# --- Defaults (mirror the BlueState-XL scenario constants) --------------------


def _default_tenant_id() -> uuid.UUID:
    # Mirrors ``control_plane.scenarios.bluestate_xl.TENANT_ID`` without
    # importing the module — keeps the runner usable from CI environments
    # that don't have control_plane on the path. The integration test
    # always passes ``tenant_id=`` explicitly so production paths never
    # hit this fallback.
    return uuid.UUID("11111111-1111-1111-1111-111111111111")


def _default_engagement_id() -> uuid.UUID:
    return uuid.UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee")


# --- CLI (ticket G1) ----------------------------------------------------------
#
# ``python -m tests.golden.agent_kenny.runner`` from services/control-plane.
# The CLI owns the full harness lifecycle so CI needs zero pytest plumbing:
# Postgres (existing DATABASE_URL or a fresh pgvector testcontainer),
# migrations, BlueState-XL seed, in-process ASGI transport, report file.


def _default_seed() -> int:
    """Deterministic default sampling seed.

    In CI this is ``GITHUB_RUN_ID`` so a nightly run can be reproduced
    locally with ``--seed <run_id>``; outside CI it is 0 so repeated
    local invocations pick the same sample unless ``--seed`` is given.
    """
    raw = os.environ.get("GITHUB_RUN_ID", "").strip()
    if raw.isdigit():
        return int(raw)
    return 0


def select_questions(
    questions: list[Question],
    *,
    question_ids: list[str] | None = None,
    limit: int | None = None,
    randomize: bool = False,
    seed: int = 0,
) -> list[Question]:
    """Resolve the CLI's selection flags into a concrete question list.

    ``question_ids`` wins outright (explicit subset, order preserved,
    unknown ids are an error). Otherwise ``--random`` samples ``limit``
    questions (or shuffles all of them) with a seeded RNG so CI runs are
    reproducible; without ``--random``, ``limit`` takes the first N in
    YAML order.
    """
    if question_ids:
        by_id = {q.id: q for q in questions}
        missing = [qid for qid in question_ids if qid not in by_id]
        if missing:
            raise ValueError(f"unknown question ids: {missing}")
        return [by_id[qid] for qid in question_ids]
    selected = list(questions)
    if randomize:
        rng = random.Random(seed)
        if limit is not None and limit < len(selected):
            return rng.sample(selected, limit)
        rng.shuffle(selected)
        return selected
    if limit is not None:
        return selected[:limit]
    return selected


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m tests.golden.agent_kenny.runner",
        description="Run the Agent Kenny golden-question eval end-to-end.",
    )
    parser.add_argument("--limit", type=int, default=None, metavar="N", help="run only N questions")
    parser.add_argument(
        "--random",
        action="store_true",
        help="sample the --limit subset randomly (seeded; see --seed) instead of taking YAML order",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        metavar="S",
        help="RNG seed for --random (default: GITHUB_RUN_ID when set, else 0)",
    )
    parser.add_argument(
        "--question-ids",
        type=str,
        default=None,
        metavar="a,b",
        help="comma-separated explicit subset (mutually exclusive with --limit/--random)",
    )
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        metavar="PATH",
        help="where to write the JSON report (default: eval-reports/agent-kenny-<ts>.json)",
    )
    parser.add_argument(
        "--runtime",
        choices=("legacy", "langgraph"),
        default="legacy",
        help="agent runtime; exported as DEPLOYAI_AGENT_RUNTIME (ticket D2 flag)",
    )
    parser.add_argument(
        "--seed-days",
        type=int,
        default=30,
        metavar="D",
        help="BlueState-XL snapshot-backfill horizon in days (default 30; production fixture uses 1825)",
    )
    parser.add_argument(
        "--questions",
        type=Path,
        default=None,
        metavar="PATH",
        help=(
            "alternate questions YAML (e.g. the G2 derived set from "
            "`python -m tests.golden.agent_kenny.derive`); default is the curated questions.yaml. "
            "Alternate files skip the 30-question distribution check."
        ),
    )
    return parser


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.question_ids and (args.limit is not None or args.random):
        parser.error("--question-ids is mutually exclusive with --limit/--random")
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be >= 1")
    if args.seed is None:
        args.seed = _default_seed()
    return args


async def _amain(args: argparse.Namespace) -> RunReport:
    """Full harness lifecycle. Returns the aggregated report.

    ``main`` writes the report file, prints the summary, and maps the
    report to the process exit code.
    """
    # Env the app reads — set BEFORE importing control_plane.main.
    os.environ["DEPLOYAI_AGENT_KENNY_V2_ENABLED"] = "1"
    os.environ["DEPLOYAI_AGENT_RUNTIME"] = args.runtime
    os.environ.setdefault("DEPLOYAI_INTERNAL_API_KEY", "agent-kenny-eval-cli")

    questions = load_questions(args.questions, enforce_distribution=args.questions is None)
    ids = [s.strip() for s in args.question_ids.split(",") if s.strip()] if args.question_ids else None
    selected = select_questions(
        questions,
        question_ids=ids,
        limit=args.limit,
        randomize=args.random,
        seed=args.seed,
    )
    print(f"selected {len(selected)}/{len(questions)} questions: {[q.id for q in selected]}")

    # Postgres: reuse an externally provided DATABASE_URL, otherwise spin
    # the same pgvector testcontainer image the integration conftest uses.
    from tests.conftest import _PGVECTOR_IMAGE, _bootstrap_extensions, _run_alembic_upgrade

    container = None
    external_url = os.environ.get("DATABASE_URL", "").strip()
    try:
        if external_url:
            db_url = _psycopg_url(external_url)
            print(f"using external DATABASE_URL ({db_url.split('@')[-1]})")
        else:
            try:
                from testcontainers.postgres import PostgresContainer  # type: ignore[import-untyped]
            except ImportError as exc:  # pragma: no cover
                raise RuntimeError("no DATABASE_URL and testcontainers not installed — run `uv sync`") from exc
            print(f"starting {_PGVECTOR_IMAGE} testcontainer (no DATABASE_URL in env)...")
            container = PostgresContainer(
                image=_PGVECTOR_IMAGE,
                username="deployai",
                password="deployai-eval",
                dbname="deployai",
            )
            container.start()
            db_url = _psycopg_url(container.get_connection_url())

        _bootstrap_extensions(db_url)
        _run_alembic_upgrade(db_url)

        os.environ["DATABASE_URL"] = db_url
        from control_plane.db import clear_engine_cache
        from control_plane.main import app
        from control_plane.scenarios.bluestate_xl import ENGAGEMENT_ID as XL_ENGAGEMENT_ID
        from control_plane.scenarios.bluestate_xl import TENANT_ID as XL_TENANT_ID
        from control_plane.scenarios.bluestate_xl.runner import apply_bluestate_xl_scenario

        clear_engine_cache()

        tenant_id = uuid.UUID(XL_TENANT_ID)
        engagement_id = uuid.UUID(XL_ENGAGEMENT_ID)

        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        seed_engine = create_async_engine(db_url)
        try:
            session_factory = async_sessionmaker(seed_engine, expire_on_commit=False)
            async with session_factory() as session:
                summary = await apply_bluestate_xl_scenario(session, tenant_id=tenant_id, days=args.seed_days)
                await session.commit()
            print(
                f"seeded BlueState-XL: {summary.ledger_event_count} ledger events, "
                f"{summary.snapshot_count} snapshots (days={args.seed_days})"
            )
        finally:
            await seed_engine.dispose()

        from httpx import ASGITransport

        transport = ASGITransport(app=app)
        client = AsyncClient(transport=transport, base_url="http://test", timeout=120.0)
        client.headers["X-DeployAI-Internal-Key"] = os.environ["DEPLOYAI_INTERNAL_API_KEY"]
        try:
            report = await run_all(
                client=client,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                write_report=False,
                questions=selected,
            )
        finally:
            await client.aclose()
            clear_engine_cache()
    finally:
        if container is not None:
            container.stop()

    return report


def _psycopg_url(url: str) -> str:
    """Normalise any postgres URL to the psycopg3 driver.

    psycopg3 serves both sides of the harness: alembic's sync engine and
    the app's async engine (same driver string the integration fixtures
    use), so one URL string works everywhere.
    """
    normalised = re.sub(r"^postgresql\+[a-z0-9]+://", "postgresql://", url)
    return normalised.replace("postgresql://", "postgresql+psycopg://", 1)


def _print_summary(report: RunReport, report_path: Path) -> None:
    print(f"\n=== Agent Kenny eval report ({report_path}) ===")
    print(f"questions: {report.total_questions}")
    print(f"pass_rate: {report.pass_rate:.2f}")
    print(f"idk_rate: {report.idk_rate:.2f}")
    print(f"hallucination_rate: {report.hallucination_rate:.2f}")
    print(f"cross_engagement_leak_count: {report.cross_engagement_leak_count}")
    print(f"latency p50/p95/p99 ms: {report.latency_p50_ms}/{report.latency_p95_ms}/{report.latency_p99_ms}")
    for r in report.results:
        verdict = "PASS" if r.expected_pass else "FAIL"
        judge = "" if r.judged_pass is None else f" judged={r.judged_pass}"
        err = f" error={r.error}" if r.error else ""
        leak = " LEAK" if r.cross_engagement_leak else ""
        print(f"  {r.id} [{r.category}] {verdict} substring={r.substring_pass}{judge}{leak}{err}")


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Exit codes: 0 = clean run; 1 = at least one
    question hit a transport/harness error; 2 = cross-engagement leak
    detected (the CI leak gate also re-checks the report with jq)."""
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = _parse_args(argv)
    report = asyncio.run(_amain(args))

    report_path: Path | None = args.report
    if report_path is None:
        ts = report.started_at.strftime("%Y%m%dT%H%M%SZ")
        report_path = _DEFAULT_REPORT_DIR / f"agent-kenny-{ts}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report.model_dump_json(indent=2), encoding="utf-8")

    _print_summary(report, report_path)

    if report.cross_engagement_leak_count > 0:
        return 2
    if any(r.error for r in report.results):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "QUESTIONS_PATH",
    "build_arg_parser",
    "load_questions",
    "main",
    "run_all",
    "run_question",
    "select_questions",
]
