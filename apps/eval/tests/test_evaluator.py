"""Unit tests for rule-based replay-parity (Story 4-5)."""

from __future__ import annotations

import json
import tempfile
import uuid
from pathlib import Path

from eval.rules.evaluator import CitationHit, compare_citations_rule_based, write_report


def _e(nid: str, must: bool = True, floor: int = 0) -> dict:
    return {"node_id": nid, "must_appear": must, "rank_floor": floor}


def test_exact_match_pass() -> None:
    u = str(uuid.uuid4())
    act = [CitationHit(node_id=uuid.UUID(u), rank=0)]
    r = compare_citations_rule_based(expected=[_e(u)], actual=act, query_id="t1")
    assert r.pass_
    assert not r.missing and not r.extra and not r.wrong_rank


def test_missing_fails() -> None:
    u = str(uuid.uuid4())
    r = compare_citations_rule_based(expected=[_e(u)], actual=[], query_id="t2")
    assert not r.pass_
    assert len(r.missing) == 1


def test_extra_fails() -> None:
    u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
    act = [CitationHit(node_id=uuid.UUID(u1), rank=0), CitationHit(node_id=uuid.UUID(u2), rank=1)]
    r = compare_citations_rule_based(expected=[_e(u1)], actual=act, query_id="t3")
    assert not r.pass_
    assert uuid.UUID(u2) in r.extra


def test_wrong_rank_fails() -> None:
    u = str(uuid.uuid4())
    act = [CitationHit(node_id=uuid.UUID(u), rank=3)]
    r = compare_citations_rule_based(expected=[_e(u, floor=1)], actual=act, query_id="t4")
    assert not r.pass_
    assert r.wrong_rank


def test_write_report_json() -> None:
    u = str(uuid.uuid4())
    rep = compare_citations_rule_based(expected=[_e(u)], actual=[], query_id="x")
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "rules-report.json"
        write_report([rep], p)
        data = json.loads(p.read_text())
        assert data["reports"][0]["query_id"] == "x"
        assert data["reports"][0]["pass"] is False
