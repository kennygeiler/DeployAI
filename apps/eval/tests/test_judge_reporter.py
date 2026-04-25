from __future__ import annotations

import json
import os
from pathlib import Path

from eval.judge.reporter import build_report_for_ci, resolve_mode, run_stub_judge, write_judge_report


def test_run_stub_judge() -> None:
    r = run_stub_judge()
    assert r.mode == "stub"
    assert r.items and r.items[0].pass_


def test_resolve_mode_default() -> None:
    os.environ.pop("DEPLOYAI_EVAL_JUDGE_MODE", None)
    assert resolve_mode() == "stub"


def test_resolve_mode_llm() -> None:
    os.environ["DEPLOYAI_EVAL_JUDGE_MODE"] = "llm"
    try:
        assert resolve_mode() == "llm"
    finally:
        os.environ.pop("DEPLOYAI_EVAL_JUDGE_MODE", None)


def test_build_report_for_ci_llm_is_placeholder() -> None:
    os.environ["DEPLOYAI_EVAL_JUDGE_MODE"] = "llm"
    try:
        r = build_report_for_ci()
        assert r.mode == "llm"
        assert r.error
        assert r.items == []
    finally:
        os.environ.pop("DEPLOYAI_EVAL_JUDGE_MODE", None)


def test_write_judge_report_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    r = run_stub_judge()
    write_judge_report(r, p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["mode"] == "stub"
    assert data["items"][0]["query_id"] == "ci-smoke-placeholder"
