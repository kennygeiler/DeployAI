"""LLM-judge report shape and writers (Story 4-6; stub path until model wiring)."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

JudgeMode = Literal["stub", "llm"]


@dataclass
class JudgeItem:
    query_id: str
    pass_: bool
    rationale: str
    scores: dict[str, float] = field(default_factory=dict)
    model: str | None = None


@dataclass
class JudgeReport:
    mode: JudgeMode
    items: list[JudgeItem] = field(default_factory=list)
    error: str | None = None


def resolve_mode() -> JudgeMode:
    raw = (os.environ.get("DEPLOYAI_EVAL_JUDGE_MODE") or "stub").strip().lower()
    if raw in ("llm", "openai", "anthropic"):
        return "llm"
    return "stub"


def run_stub_judge() -> JudgeReport:
    return JudgeReport(
        mode="stub",
        items=[
            JudgeItem(
                query_id="ci-smoke-placeholder",
                pass_=True,
                rationale="Stub judge (set DEPLOYAI_EVAL_JUDGE_MODE=llm and wire the provider in a later pass).",
                scores={"relevance": 1.0, "faithfulness": 1.0},
            )
        ],
    )


def run_llm_judge_placeholder() -> JudgeReport:
    return JudgeReport(
        mode="llm",
        error="LLM judge not wired: provide adapter + prompts (Story 4-6 follow-up).",
        items=[],
    )


def write_judge_report(report: JudgeReport, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "mode": report.mode,
        "error": report.error,
        "items": [
            {
                "query_id": i.query_id,
                "pass": i.pass_,
                "rationale": i.rationale,
                "scores": i.scores,
                "model": i.model,
            }
            for i in report.items
        ],
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_report_for_ci() -> JudgeReport:
    if resolve_mode() == "llm":
        return run_llm_judge_placeholder()
    return run_stub_judge()
