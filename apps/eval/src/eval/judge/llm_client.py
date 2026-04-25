"""Anthropic Messages API for tier-2 judge (Epic 4, Story 4-6)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any, cast

import httpx

from eval.judge.prompts import JUDGE_SYSTEM_V0
from eval.judge.reporter import JudgeItem


class AnthropicError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


def _first_text_from_message_payload(data: dict[str, Any]) -> str:
    blocks = data.get("content")
    if not isinstance(blocks, list):
        msg = f"Unexpected Anthropic response (content): {data!r}"
        raise AnthropicError(msg)
    for block in blocks:
        if isinstance(block, dict) and block.get("type") == "text" and "text" in block:
            return str(block["text"])
    msg = f"No text content block in Anthropic response: {data!r}"
    raise AnthropicError(msg)


def _anthropic_api_key() -> str:
    return (os.environ.get("ANTHROPIC_API_KEY") or "").strip()


def _anthropic_model() -> str:
    return (os.environ.get("ANTHROPIC_MODEL") or "claude-3-5-haiku-20241022").strip()


def extract_first_json_object(text: str) -> dict[str, Any]:
    """Parse the first top-level JSON object from model output (prose or ``` fences)."""
    s = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", s, re.IGNORECASE)
    if fence:
        s = fence.group(1).strip()
    start = s.find("{")
    if start < 0:
        msg = "No JSON object found in model output"
        raise ValueError(msg)
    decoder = json.JSONDecoder()
    try:
        obj, _end = decoder.raw_decode(s, start)
    except json.JSONDecodeError as e:
        msg = f"Invalid JSON: {e}"
        raise ValueError(msg) from e
    if not isinstance(obj, dict):
        msg = "Judge output root must be a JSON object"
        raise ValueError(msg)
    return obj


def _judge_user_message(*, query_id: str, golden: object, actual: object) -> str:
    return (
        "Compare the agent retrieval result to the golden (expected) citations.\n\n"
        f"query_id: {query_id!r}\n\n"
        f"golden (expected): {json.dumps(golden, indent=2)}\n\n"
        f"agent (actual): {json.dumps(actual, indent=2)}\n\n"
        "Respond with a single JSON object only, using this exact shape:\n"
        '{"query_id": "<same as input>", "pass": <bool>, "rationale": "<short>", '
        '"scores": {"relevance": <0-1 float>, "faithfulness": <0-1 float>}}\n'
    )


def default_smoke_judge_input() -> dict[str, Any]:
    """When no file/env override is set — deterministic CI-friendly payload."""
    sid = "00000000-0000-4000-8000-000000000001"
    return {
        "query_id": "ci-smoke",
        "expected_citations": [{"node_id": sid, "rank_floor": 0, "must_appear": True}],
        "actual_citations": [{"node_id": sid, "rank": 0}],
    }


def load_judge_input_dict() -> dict[str, Any]:
    raw = (os.environ.get("DEPLOYAI_EVAL_JUDGE_INPUT") or "").strip()
    if raw:
        p = _resolve_path(raw)
        if not p.is_file():
            msg = f"DEPLOYAI_EVAL_JUDGE_INPUT is not a file: {p}"
            raise FileNotFoundError(msg)
        return cast(dict[str, Any], json.loads(p.read_text(encoding="utf-8")))
    root = _repo_root_from_env()
    candidate = root / "artifacts" / "replay-parity" / "judge-input.json"
    if candidate.is_file():
        return cast(dict[str, Any], json.loads(candidate.read_text(encoding="utf-8")))
    return default_smoke_judge_input()


def _resolve_path(s: str) -> Path:
    return Path(s).expanduser().resolve()


def _repo_root_from_env() -> Path:
    override = (os.environ.get("DEPLOYAI_MONOREPO_ROOT") or "").strip()
    if override:
        return Path(override).resolve()
    # eval/judge/llm_client.py -> parents[4] = monorepo root
    return Path(__file__).resolve().parents[4]


def invoke_anthropic_judge() -> tuple[JudgeItem, str | None]:
    """
    One Messages call. Returns (JudgeItem, model_id).

    Raises AnthropicError on HTTP / contract failures.
    """
    key = _anthropic_api_key()
    if not key:
        msg = "ANTHROPIC_API_KEY is not set"
        raise AnthropicError(msg)

    payload = load_judge_input_dict()
    qid = str(payload.get("query_id") or "query")
    golden = payload.get("expected_citations", payload.get("golden", []))
    actual = payload.get("actual_citations", payload.get("actual", []))
    user = _judge_user_message(query_id=qid, golden=golden, actual=actual)

    model = _anthropic_model()
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model,
                    "max_tokens": 1024,
                    "system": JUDGE_SYSTEM_V0,
                    "messages": [{"role": "user", "content": user}],
                },
            )
    except httpx.HTTPError as e:
        msg = f"Anthropic request failed: {e}"
        raise AnthropicError(msg) from e
    if r.status_code >= 400:
        msg = f"Anthropic API error {r.status_code}: {r.text[:500]}"
        raise AnthropicError(msg)
    data = r.json()
    if not isinstance(data, dict):
        msg = f"Unexpected Anthropic response (not an object): {data!r}"
        raise AnthropicError(msg)
    text = _first_text_from_message_payload(data)

    try:
        obj = extract_first_json_object(text)
    except (json.JSONDecodeError, ValueError) as e:
        msg = f"Failed to parse judge JSON: {e}; snippet={text[:400]!r}"
        raise AnthropicError(msg) from e

    out_qid = str(obj.get("query_id", qid))
    pass_ = bool(obj.get("pass", False))
    rationale = str(obj.get("rationale", ""))
    raw_scores = obj.get("scores")
    scores: dict[str, float] = {}
    if isinstance(raw_scores, dict):
        for k, v in raw_scores.items():
            if isinstance(v, (int, float)):
                scores[str(k)] = float(v)

    return (
        JudgeItem(
            query_id=out_qid,
            pass_=pass_,
            rationale=rationale,
            scores=scores,
            model=model,
        ),
        model,
    )
