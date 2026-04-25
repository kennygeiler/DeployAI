"""Tier-1 rule-based replay-parity: exact node_id + rank-floor (Story 4-5, epics)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID


@dataclass
class CitationHit:
    node_id: UUID
    rank: int  # 0 = best


@dataclass
class RuleEvalReport:
    query_id: str
    pass_: bool
    missing: list[UUID] = field(default_factory=list)
    extra: list[UUID] = field(default_factory=list)
    wrong_rank: list[dict[str, Any]] = field(default_factory=list)


def compare_citations_rule_based(
    *,
    expected: list[dict[str, Any]],
    actual: list[CitationHit],
    query_id: str = "query",
) -> RuleEvalReport:
    """
    ``expected`` rows: { node_id, must_appear, rank_floor } from golden YAML.
    ``actual`` ordered by decreasing relevance (rank 0 = first).
    """
    rep = RuleEvalReport(query_id=query_id, pass_=True)
    if not expected:
        return rep

    actual_by_id: dict[UUID, int] = {}
    for h in actual:
        actual_by_id[h.node_id] = h.rank

    for row in expected:
        if not row.get("must_appear", True):
            continue
        eid = UUID(str(row["node_id"]))
        floor = int(row.get("rank_floor", 0))
        if eid not in actual_by_id:
            rep.missing.append(eid)
            rep.pass_ = False
        elif int(actual_by_id[eid]) > floor:
            rep.wrong_rank.append({"node_id": str(eid), "actual_rank": actual_by_id[eid], "floor": floor})
            rep.pass_ = False

    expected_ids = {UUID(str(x["node_id"])) for x in expected if x.get("must_appear", True)}
    for h in actual:
        if h.node_id not in expected_ids:
            rep.extra.append(h.node_id)
            rep.pass_ = False

    return rep


def write_report(reports: list[RuleEvalReport], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "reports": [
            {
                "query_id": r.query_id,
                "pass": r.pass_,
                "missing": [str(x) for x in r.missing],
                "extra": [str(x) for x in r.extra],
                "wrong_rank": r.wrong_rank,
            }
            for r in reports
        ]
    }
    out_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
