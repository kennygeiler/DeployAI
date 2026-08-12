"""Pydantic models for the Agent Kenny v2 golden-question eval harness.

The three models cover (scope-v2 §11.2):

- :class:`Question` — one entry from ``questions.yaml`` after validation.
- :class:`QuestionResult` — per-question metrics produced by ``run_question``.
- :class:`RunReport` — aggregate metrics + per-question results written by
  ``run_all`` to ``eval-reports/agent-kenny-{timestamp}.json``.

These models live OUTSIDE the production tree on purpose — the eval
harness is test infrastructure, not a production service.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CATEGORIES: tuple[str, ...] = (
    "direct_lookup",
    "causal_chain",
    "negative",
    "cross_engagement",
    "multi_hop",
    "temporal",
)
"""Closed set of question categories.

The first five are fixed across Phase 6 Waves A/B/C; ``temporal`` was
added by ticket G2 for derived what-changed-in-week-N questions and does
not appear in the curated 30 (the distribution below stays untouched).
"""

# scope-v2 §11.1 — fixed distribution; the runner asserts the YAML matches.
EXPECTED_DISTRIBUTION: dict[str, int] = {
    "direct_lookup": 8,
    "causal_chain": 8,
    "negative": 6,
    "cross_engagement": 4,
    "multi_hop": 4,
}

CitationKind = Literal["event", "node", "insight", "turn", "edge", "slack", "linear", "gdrive", "notion", "github"]
Category = Literal["direct_lookup", "causal_chain", "negative", "cross_engagement", "multi_hop", "temporal"]
Difficulty = Literal["easy", "medium", "hard"]


class Question(BaseModel):
    """One golden question — hand-curated (questions.yaml) or derived (G2)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64)
    category: Category
    question: str = Field(min_length=1, max_length=4000)
    expected_answer_contains: list[str] = Field(default_factory=list)
    expected_min_citations: int = Field(ge=0)
    expected_kinds: list[CitationKind] = Field(default_factory=list)
    should_idk: bool
    # Negative controls expect a decline: an answer with zero citations is
    # the CORRECT outcome, so the hallucination denominator fix (ticket G4)
    # must not count their citation-free replies as unverified.
    is_negative_control: bool = False
    # --- Derived-question metadata (ticket G2; absent on the curated 30) ------
    # Seeded UUIDs (as strings) the answer's citations should include —
    # ledger event ids, matrix node ids, or insight ids, all derivable
    # from the deterministic XL generator.
    expected_citation_ids: list[str] = Field(default_factory=list)
    # Which derivation template produced this question (e.g. "sponsor_lookup").
    template: str | None = None
    difficulty: Difficulty | None = None
    # Earliest engagement week (1-based) by which every fact this question
    # relies on exists in the corpus. The longitudinal replay (ticket G3)
    # only asks a question at checkpoints whose horizon covers this week.
    valid_from_week: int | None = Field(default=None, ge=1)


class QuestionResult(BaseModel):
    """Per-question metrics captured from one stream-v2 run.

    Fields mirror the scope-v2 §11.2 spec one-for-one so the Wave C
    dashboard can render straight from this payload without a second
    transform layer.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    category: Category
    latency_ms: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    citations_total: int = Field(ge=0)
    citations_verified: int = Field(ge=0)
    citations_unverified: int = Field(ge=0)
    citations_external: int = Field(ge=0)
    revisions: int = Field(ge=0)
    adversarial_concerns: int = Field(ge=0)
    idk: bool
    final_text: str
    expected_pass: bool
    expected_kind_match: bool
    cross_engagement_leak: bool
    error: str | None = None
    # Ticket G4 — honest pass metrics. ``substring_pass`` is the cheap
    # case-insensitive substring check; ``judged_pass`` is the optional
    # LLM-judge verdict (None = judge not run: disabled, stub provider,
    # or the substring check already passed). ``expected_pass`` remains
    # the headline verdict: substring_pass OR judged_pass is True.
    substring_pass: bool = False
    judged_pass: bool | None = None
    # Mirrored from the question so aggregation can exempt negative
    # controls from the zero-citation hallucination penalty.
    is_negative_control: bool = False
    # Ticket G2 — citation-id ground truth. How many of the question's
    # ``expected_citation_ids`` were actually cited in the reply stream
    # (any citation frame kind). Both zero when the question carries no
    # expected ids (the curated 30).
    expected_citation_ids_total: int = Field(default=0, ge=0)
    expected_citation_ids_matched: int = Field(default=0, ge=0)


class CategoryDistribution(BaseModel):
    """Aggregate per-category roll-up included in :class:`RunReport`."""

    model_config = ConfigDict(extra="forbid")

    category: Category
    total: int
    passes: int
    idk: int
    leaks: int
    pass_rate: float


class RunReport(BaseModel):
    """Aggregate report written to ``eval-reports/agent-kenny-{timestamp}.json``."""

    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    finished_at: datetime
    total_questions: int
    pass_rate: float
    idk_rate: float
    hallucination_rate: float
    cross_engagement_leak_count: int
    latency_p50_ms: int
    latency_p95_ms: int
    latency_p99_ms: int
    by_category: list[CategoryDistribution]
    results: list[QuestionResult]


class CheckpointReport(BaseModel):
    """Metrics for one longitudinal checkpoint (ticket G3)."""

    model_config = ConfigDict(extra="forbid")

    checkpoint_days: int = Field(ge=1)
    horizon_weeks: int = Field(ge=1)
    eligible_questions: int = Field(ge=0)
    questions_run: int = Field(ge=0)
    question_ids: list[str]
    pass_rate: float
    # Fraction of expected seeded citation ids actually cited, across the
    # subset's questions that carry expected ids. None when none do.
    citation_precision: float | None
    latency_p50_ms: int = Field(ge=0)
    latency_p95_ms: int = Field(ge=0)
    cross_engagement_leak_count: int = Field(ge=0)
    run: RunReport


class LongitudinalReport(BaseModel):
    """Aggregate longitudinal replay report (ticket G3).

    The degradation contract: ``degraded`` is True when any checkpoint's
    pass_rate drops more than ``tolerance`` below the best pass_rate of
    any EARLIER (shorter-horizon) checkpoint. The CLI exits 3 on
    degradation and 2 on any cross-engagement leak.
    """

    model_config = ConfigDict(extra="forbid")

    started_at: datetime
    finished_at: datetime
    seed: int
    per_checkpoint: int
    tolerance: float
    questions_source: str
    checkpoints: list[CheckpointReport]
    total_leaks: int = Field(ge=0)
    degraded: bool
    degradation_notes: list[str]


__all__ = [
    "CATEGORIES",
    "EXPECTED_DISTRIBUTION",
    "Category",
    "CategoryDistribution",
    "CheckpointReport",
    "CitationKind",
    "Difficulty",
    "LongitudinalReport",
    "Question",
    "QuestionResult",
    "RunReport",
]
