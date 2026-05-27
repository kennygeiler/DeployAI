"""Agent Kenny v2 golden-question eval harness (scope-v2 §11, Phase 6 Wave A).

Public surface:

- :class:`Question` / :class:`QuestionResult` / :class:`RunReport` —
  Pydantic models for the YAML schema + runner output.
- :func:`load_questions` — read + validate the curated YAML file.
- :func:`run_question` — drive ONE question through Agent Kenny via the
  stream-v2 SSE endpoint.
- :func:`run_all` — seed BlueState-XL, run every question (or a subset),
  aggregate metrics, and write a JSON report to ``eval-reports/``.

Wave A ships the harness only. Wave B wires this into CI; Wave C
surfaces the aggregate metrics on an admin dashboard.
"""

from __future__ import annotations

from .runner import load_questions, run_all, run_question
from .types import CategoryDistribution, Question, QuestionResult, RunReport

__all__ = [
    "CategoryDistribution",
    "Question",
    "QuestionResult",
    "RunReport",
    "load_questions",
    "run_all",
    "run_question",
]
