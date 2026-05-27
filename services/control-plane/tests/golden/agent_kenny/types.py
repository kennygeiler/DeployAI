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
)
"""Closed set of question categories. Fixed across Phase 6 Waves A/B/C."""

# scope-v2 §11.1 — fixed distribution; the runner asserts the YAML matches.
EXPECTED_DISTRIBUTION: dict[str, int] = {
    "direct_lookup": 8,
    "causal_chain": 8,
    "negative": 6,
    "cross_engagement": 4,
    "multi_hop": 4,
}

CitationKind = Literal["event", "node", "insight", "turn", "edge", "slack", "linear", "gdrive", "notion", "github"]
Category = Literal["direct_lookup", "causal_chain", "negative", "cross_engagement", "multi_hop"]


class Question(BaseModel):
    """One curated golden question."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str = Field(min_length=1, max_length=64)
    category: Category
    question: str = Field(min_length=1, max_length=4000)
    expected_answer_contains: list[str] = Field(default_factory=list)
    expected_min_citations: int = Field(ge=0)
    expected_kinds: list[CitationKind] = Field(default_factory=list)
    should_idk: bool


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


__all__ = [
    "CATEGORIES",
    "EXPECTED_DISTRIBUTION",
    "Category",
    "CategoryDistribution",
    "CitationKind",
    "Question",
    "QuestionResult",
    "RunReport",
]
