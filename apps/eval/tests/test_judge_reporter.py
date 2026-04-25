from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from eval.judge.llm_client import _first_text_from_message_payload, extract_first_json_object
from eval.judge.reporter import JudgeItem, build_report_for_ci, resolve_mode, run_stub_judge, write_judge_report


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


def test_build_report_for_ci_llm_errors_without_key() -> None:
    os.environ["DEPLOYAI_EVAL_JUDGE_MODE"] = "llm"
    os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        r = build_report_for_ci()
        assert r.mode == "llm"
        assert r.error
        assert "ANTHROPIC_API_KEY" in r.error
        assert r.items == []
    finally:
        os.environ.pop("DEPLOYAI_EVAL_JUDGE_MODE", None)


def test_build_report_for_ci_llm_success_patched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    os.environ["DEPLOYAI_EVAL_JUDGE_MODE"] = "llm"
    os.environ["ANTHROPIC_API_KEY"] = "fake"

    def _fake() -> tuple[JudgeItem, str | None]:
        return (
            JudgeItem(
                query_id="q1",
                pass_=True,
                rationale="ok",
                scores={"relevance": 0.9},
                model="claude-3-5-haiku-20241022",
            ),
            "claude-3-5-haiku-20241022",
        )

    monkeypatch.setattr("eval.judge.llm_client.invoke_anthropic_judge", _fake)
    try:
        r = build_report_for_ci()
        assert r.mode == "llm"
        assert not r.error
        assert r.items[0].query_id == "q1"
    finally:
        os.environ.pop("DEPLOYAI_EVAL_JUDGE_MODE", None)
        os.environ.pop("ANTHROPIC_API_KEY", None)


def test_extract_first_json_object_fenced() -> None:
    text = 'Here:\n```json\n{"a": 1, "b": true}\n```\n'
    assert extract_first_json_object(text) == {"a": 1, "b": True}


def test_extract_first_json_object_braces_in_string() -> None:
    """Brace-counting would fail; raw_decode must respect JSON string rules."""
    text = '{"query_id": "a{b}c", "pass": true, "rationale": "ok", "scores": {}}'
    o = extract_first_json_object("prefix " + text)
    assert o["query_id"] == "a{b}c"
    assert o["pass"] is True


def test_anthropic_first_text_skips_thinking() -> None:
    data = {
        "content": [
            {"type": "thinking", "thinking": "x"},
            {"type": "text", "text": '{"pass": true}'},
        ]
    }
    t = _first_text_from_message_payload(data)
    assert t == '{"pass": true}'


def test_load_judge_input_missing_file_errors(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from eval.judge import llm_client

    p = tmp_path / "nope.json"
    monkeypatch.setenv("DEPLOYAI_EVAL_JUDGE_INPUT", str(p))
    try:
        llm_client.load_judge_input_dict()
    except FileNotFoundError as e:
        assert "DEPLOYAI_EVAL_JUDGE_INPUT" in str(e)
    else:
        raise AssertionError("expected FileNotFoundError")
    finally:
        monkeypatch.delenv("DEPLOYAI_EVAL_JUDGE_INPUT", raising=False)


def test_write_judge_report_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "judge.json"
    r = run_stub_judge()
    write_judge_report(r, p)
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data["mode"] == "stub"
    assert data["items"][0]["query_id"] == "ci-smoke-placeholder"
