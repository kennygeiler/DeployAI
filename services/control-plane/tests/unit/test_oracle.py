"""Unit tests for the Phase 7 Oracle synthesis agent.

Pure function — no DB, no FastAPI. Predicates run deterministically; the
fake LLM returns hand-crafted JSON for the phrasing step.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed

from control_plane.agents.oracle import (
    EdgeSnapshot,
    EventSnapshot,
    NodeSnapshot,
    oracle_candidates,
    oracle_phrase,
    run_oracle,
)


class _FakeLLM:
    """Returns a fixed string; records the last messages it saw."""

    id = "fake"

    def __init__(self, response: str = "[]") -> None:
        self.response = response
        self.last_messages: list[ChatMessage] | None = None
        self.call_count = 0

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = temperature, max_output_tokens
        self.last_messages = messages
        self.call_count += 1
        return self.response

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = messages, temperature, max_output_tokens
        for chunk in (self.chat_complete(messages),):
            yield chunk

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


# Stable ids for repeatable assertions.
_ENG = uuid.UUID("00000000-0000-7000-8000-000000000001")
_NOW = datetime(2026, 5, 23, 12, 0, tzinfo=UTC)


def _node(
    *,
    id_: uuid.UUID,
    node_type: str,
    title: str,
    attributes: dict | None = None,
    evidence: tuple[uuid.UUID, ...] = (),
) -> NodeSnapshot:
    return NodeSnapshot(
        id=id_,
        node_type=node_type,
        title=title,
        attributes=attributes or {},
        evidence_event_ids=evidence,
    )


def _evt(*, id_: uuid.UUID, days_ago: int, text: str = "evt") -> EventSnapshot:
    return EventSnapshot(
        id=id_,
        occurred_at=_NOW - timedelta(days=days_ago),
        event_type="email",
        text=text,
    )


def test_no_candidates_returns_empty_and_skips_llm() -> None:
    llm = _FakeLLM(response='[{"title":"x","body":"y"}]')
    drafts = run_oracle(
        engagement_id=_ENG,
        engagement_name="eng",
        engagement_phase="discovery",
        nodes=[],
        edges=[],
        recent_events=[],
        llm=llm,
        now=_NOW,
    )
    assert drafts == []
    assert llm.call_count == 0  # no candidates → no LLM call


def test_predicate_stale_commitment_flags_old_event() -> None:
    nid = uuid.uuid4()
    eid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot", evidence=(eid,))],
        edges=[],
        recent_events=[_evt(id_=eid, days_ago=20)],
        now=_NOW,
    )
    assert len(cands) == 1
    c = cands[0]
    assert c.insight_type == "stale_commitment"
    assert c.severity == "medium"  # 14 <= 20 < 30
    assert c.citation_node_ids == (nid,)
    assert c.dedup_key.startswith("oracle:")
    assert "stale_commitment" in c.dedup_key
    assert c.input_hash  # non-empty hash


def test_predicate_stale_commitment_skips_fresh() -> None:
    nid = uuid.uuid4()
    eid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot", evidence=(eid,))],
        edges=[],
        recent_events=[_evt(id_=eid, days_ago=3)],
        now=_NOW,
    )
    assert cands == []  # 3d < 14d threshold


def test_predicate_stale_commitment_no_events_is_high() -> None:
    nid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot")],
        edges=[],
        recent_events=[],
        now=_NOW,
    )
    assert len(cands) == 1
    assert cands[0].severity == "high"


def test_predicate_unanswered_risk_with_mitigation_is_skipped() -> None:
    rid = uuid.uuid4()
    cid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[
            _node(id_=rid, node_type="risk", title="data residency"),
            _node(id_=cid, node_type="commitment", title="US-only hosting"),
        ],
        edges=[
            EdgeSnapshot(id=uuid.uuid4(), edge_type="blocks", from_node_id=rid, to_node_id=cid),
        ],
        recent_events=[],
        now=_NOW,
    )
    types = {c.insight_type for c in cands}
    assert "unanswered_risk" not in types


def test_predicate_unanswered_risk_without_mitigation_fires() -> None:
    rid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[_node(id_=rid, node_type="risk", title="data residency")],
        edges=[],
        recent_events=[],
        now=_NOW,
    )
    types = {c.insight_type for c in cands}
    assert "unanswered_risk" in types


def test_predicate_decision_without_owner_fires_when_no_sponsor_edge() -> None:
    did = uuid.uuid4()
    sid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[
            _node(id_=did, node_type="decision", title="pick vendor"),
            _node(id_=sid, node_type="stakeholder", title="Priya"),
        ],
        edges=[],
        recent_events=[],
        now=_NOW,
    )
    types = {c.insight_type for c in cands}
    assert "decision_without_owner" in types


def test_predicate_decision_with_sponsor_skipped() -> None:
    did = uuid.uuid4()
    sid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[
            _node(id_=did, node_type="decision", title="pick vendor"),
            _node(id_=sid, node_type="stakeholder", title="Priya"),
        ],
        edges=[
            EdgeSnapshot(id=uuid.uuid4(), edge_type="sponsors", from_node_id=sid, to_node_id=did),
        ],
        recent_events=[],
        now=_NOW,
    )
    types = {c.insight_type for c in cands}
    assert "decision_without_owner" not in types


def test_predicate_stakeholder_neglect_uses_first_when_no_explicit_sponsor() -> None:
    sid = uuid.uuid4()
    sid2 = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[
            _node(id_=sid, node_type="stakeholder", title="Dana"),
            _node(id_=sid2, node_type="stakeholder", title="Priya"),
        ],
        edges=[],
        recent_events=[],
        now=_NOW,
    )
    types = {c.insight_type for c in cands}
    assert "stakeholder_neglect" in types
    # Only the first stakeholder should fire (de facto sponsor heuristic).
    neglect_cands = [c for c in cands if c.insight_type == "stakeholder_neglect"]
    assert len(neglect_cands) == 1
    assert sid in neglect_cands[0].citation_node_ids


def test_predicate_stakeholder_neglect_uses_explicit_is_sponsor() -> None:
    sid = uuid.uuid4()
    sid2 = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[
            _node(id_=sid, node_type="stakeholder", title="Dana"),
            _node(
                id_=sid2,
                node_type="stakeholder",
                title="Priya",
                attributes={"is_sponsor": True},
            ),
        ],
        edges=[],
        recent_events=[],
        now=_NOW,
    )
    neglect = [c for c in cands if c.insight_type == "stakeholder_neglect"]
    assert len(neglect) == 1
    assert sid2 in neglect[0].citation_node_ids  # explicit sponsor wins


def test_dedup_key_is_stable_across_runs() -> None:
    nid = uuid.uuid4()
    args = dict(
        engagement_id=_ENG,
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot")],
        edges=[],
        recent_events=[],
        now=_NOW,
    )
    a = oracle_candidates(**args)
    b = oracle_candidates(**args)
    assert a[0].dedup_key == b[0].dedup_key
    assert a[0].input_hash == b[0].input_hash


def test_oracle_phrase_zips_llm_response_to_drafts() -> None:
    nid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot")],
        edges=[],
        recent_events=[],
        now=_NOW,
    )
    llm = _FakeLLM(
        response=json.dumps(
            [
                {
                    "title": "Pilot ship date is slipping",
                    "body": "No event in 30+ days. Confirm a date with the sponsor by EOD.",
                }
            ]
        )
    )
    drafts = oracle_phrase(
        engagement_name="Acme",
        engagement_phase="pilot",
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot")],
        edges=[],
        candidates=cands,
        llm=llm,
    )
    assert len(drafts) == 1
    assert drafts[0].title.startswith("Pilot ship date")
    assert drafts[0].insight_type == "stale_commitment"
    assert drafts[0].dedup_key == cands[0].dedup_key
    assert llm.call_count == 1


def test_oracle_phrase_drops_empty_title_rows() -> None:
    nid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot")],
        edges=[],
        recent_events=[],
        now=_NOW,
    )
    llm = _FakeLLM(response=json.dumps([{"title": "", "body": "x"}]))
    drafts = oracle_phrase(
        engagement_name="Acme",
        engagement_phase="pilot",
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot")],
        edges=[],
        candidates=cands,
        llm=llm,
    )
    assert drafts == []  # empty title = LLM dropped the candidate


def test_oracle_phrase_handles_bad_json() -> None:
    nid = uuid.uuid4()
    cands = oracle_candidates(
        engagement_id=_ENG,
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot")],
        edges=[],
        recent_events=[],
        now=_NOW,
    )
    llm = _FakeLLM(response="not json at all")
    drafts = oracle_phrase(
        engagement_name="Acme",
        engagement_phase="pilot",
        nodes=[_node(id_=nid, node_type="commitment", title="ship pilot")],
        edges=[],
        candidates=cands,
        llm=llm,
    )
    assert drafts == []


def test_oracle_phrase_returns_empty_when_no_candidates() -> None:
    llm = _FakeLLM(response="[]")
    drafts = oracle_phrase(
        engagement_name="Acme",
        engagement_phase="pilot",
        nodes=[],
        edges=[],
        candidates=[],
        llm=llm,
    )
    assert drafts == []
    assert llm.call_count == 0  # short-circuited before LLM
