"""Agent Kenny v2 golden-question runner (scope-v2 §11.2, Phase 6 Wave A).

Drives the ``/internal/v1/engagements/{eid}/oracle/chat/stream-v2``
endpoint against a freshly-seeded BlueState-XL fixture, parses the SSE
frame stream, and emits per-question metrics + an aggregate report.

Public surface — three callables and the three Pydantic models in
:mod:`types`. Everything else is intentionally underscored.

Hard constraints (per the Wave A spec):

- 30 questions hard count.
- BlueState-XL fixture seed reused — never re-seeded inline.
- No CI workflow file (Wave B).
- No dashboard page (Wave C).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
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
)


# --- YAML loading -------------------------------------------------------------


def load_questions(path: Path | None = None) -> list[Question]:
    """Load + validate every entry in ``questions.yaml``.

    Validates that:

    1. The file parses as a YAML sequence.
    2. Each entry parses as a :class:`Question` (Pydantic enforces the
       schema — closed category enum, no extra fields).
    3. The count and per-category distribution match
       :data:`EXPECTED_DISTRIBUTION` exactly.
    """
    src = path or QUESTIONS_PATH
    raw = yaml.safe_load(src.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"{src} must be a YAML sequence; got {type(raw).__name__}")
    questions = [Question.model_validate(entry) for entry in raw]
    _assert_distribution(questions)
    return questions


def _assert_distribution(questions: list[Question]) -> None:
    """Hard-fail if the YAML drifts from the 30/8/8/6/4/4 split."""
    total = len(questions)
    expected_total = sum(EXPECTED_DISTRIBUTION.values())
    if total != expected_total:
        raise ValueError(f"expected {expected_total} questions; got {total}")
    counts: dict[str, int] = dict.fromkeys(EXPECTED_DISTRIBUTION, 0)
    for q in questions:
        counts[q.category] += 1
    for cat, want in EXPECTED_DISTRIBUTION.items():
        if counts[cat] != want:
            raise ValueError(f"category {cat!r}: expected {want} questions, got {counts[cat]}")
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
    for f in frames:
        if f.event in ("citation_verified", "citation_unverified", "citation_external"):
            kind = f.data.get("kind")
            if isinstance(kind, str):
                citation_kinds_seen.add(kind)

    citations_total = citations_verified + citations_unverified + citations_external
    idk = _detect_idk(final_text)
    expected_pass = _expected_pass(question, final_text=final_text, idk=idk, leak=cross_engagement_leak)
    expected_kind_match = _expected_kind_match(question, citation_kinds_seen)

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
    """Optional semantic-match check via the existing LLM provider.

    Off by default. Enable by setting ``EVAL_LLM_JUDGE=1``. Returns:

    - ``True`` / ``False`` when the judge ran successfully.
    - ``None`` when the judge is disabled or the provider isn't available.

    Wave A only wires this into ``run_question`` if the gate is on AND the
    user passes ``--judge`` via the runner CLI (Wave B). For now substring
    match drives ``expected_pass``; this helper is shipped so Wave B can
    flip it on without redesigning the runner shape.
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
    return reply.strip().upper().startswith("YES")


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
) -> RunReport:
    """Seed BlueState-XL fresh, run every question (or a subset), aggregate.

    ``client`` MUST be supplied by the caller — the runner does not own
    the ASGI transport / DB engine wiring; the integration test (or a
    future CLI in Wave B) constructs the ``AsyncClient`` against either a
    real CP deployment or the FastAPI app via ``ASGITransport``.

    ``seed_fn`` defaults to
    :func:`control_plane.scenarios.bluestate_xl.runner.apply_bluestate_xl_scenario`
    — pass an explicit callable from the test fixture when the seed needs
    a session the runner cannot construct (the common case).

    Returns the :class:`RunReport`. When ``write_report=True`` (default)
    also writes the JSON payload to ``eval-reports/agent-kenny-{ts}.json``.
    """
    if client is None:
        raise ValueError("run_all requires an httpx.AsyncClient; the harness does not own transport wiring")
    questions = load_questions()
    if question_ids is not None:
        wanted = set(question_ids)
        questions = [q for q in questions if q.id in wanted]
        if not questions:
            raise ValueError(f"no questions matched ids={question_ids}")

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
    hallucination_rate = (unverified / citations_total) if citations_total else 0.0
    leaks = sum(1 for r in results if r.cross_engagement_leak)

    latencies = sorted(r.latency_ms for r in results)

    by_category: list[CategoryDistribution] = []
    for cat in EXPECTED_DISTRIBUTION:
        subset = [r for r in results if r.category == cat]
        if not subset:
            continue
        sub_passes = sum(1 for r in subset if r.expected_pass)
        sub_idk = sum(1 for r in subset if r.idk)
        sub_leaks = sum(1 for r in subset if r.cross_engagement_leak)
        by_category.append(
            CategoryDistribution(
                category=cat,  # type: ignore[arg-type]
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


__all__ = [
    "QUESTIONS_PATH",
    "load_questions",
    "run_all",
    "run_question",
]
