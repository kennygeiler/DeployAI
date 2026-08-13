"""Unit: gap_detection rules over fixture matrices (Wave 5, GA1)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.matrix import MatrixEdge, MatrixNode
from control_plane.services.gap_detection import GapAsk, detect_gaps, gap_ask_id

NOW = datetime(2026, 8, 13, 12, 0, tzinfo=UTC)
TENANT = uuid.uuid4()
ENGAGEMENT = uuid.uuid4()


def _node(node_type: str, title: str, **kw: Any) -> MatrixNode:
    return MatrixNode(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        engagement_id=ENGAGEMENT,
        node_type=node_type,
        title=title,
        attributes=kw.pop("attributes", {}),
        status=kw.pop("status", None),
        evidence_event_ids=kw.pop("evidence_event_ids", []),
        **kw,
    )


def _edge(edge_type: str, from_node: MatrixNode, to_node: MatrixNode) -> MatrixEdge:
    return MatrixEdge(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        engagement_id=ENGAGEMENT,
        edge_type=edge_type,
        from_node_id=from_node.id,
        to_node_id=to_node.id,
        attributes={},
        evidence_event_ids=[],
    )


def _event(occurred_at: datetime) -> CanonicalMemoryEvent:
    return CanonicalMemoryEvent(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        engagement_id=ENGAGEMENT,
        event_type="ingest.meeting_note",
        occurred_at=occurred_at,
        payload={},
    )


def _by_rule(asks: list[GapAsk], rule: str) -> list[GapAsk]:
    return [a for a in asks if a.rule == rule]


def _sponsored_baseline() -> tuple[list[MatrixNode], list[MatrixEdge]]:
    """A matrix that satisfies the sponsor rule so other rules test cleanly."""
    sponsor = _node("stakeholder", "Dana Vance", attributes={"is_sponsor": True})
    return [sponsor], []


def test_commitment_without_owed_by_asks_for_owner() -> None:
    nodes, edges = _sponsored_baseline()
    commitment = _node("commitment", "Pilot launch by W24")
    nodes.append(commitment)
    recent = _event(NOW - timedelta(days=1))
    commitment.evidence_event_ids = [recent.id]

    asks = detect_gaps(nodes, edges, [recent], NOW, NOW)

    owner_asks = _by_rule(asks, "commitment_no_owner")
    assert len(owner_asks) == 1
    ask = owner_asks[0]
    assert ask.target_node_id == commitment.id
    assert ask.remedy_kind == "answer"
    assert ask.id == gap_ask_id("commitment_no_owner", commitment.id)


def test_commitment_with_owed_by_edge_is_owned() -> None:
    nodes, edges = _sponsored_baseline()
    commitment = _node("commitment", "Pilot launch by W24")
    owner = _node("stakeholder", "Priya Patel")
    nodes += [commitment, owner]
    edges.append(_edge("owed_by", commitment, owner))
    recent = _event(NOW - timedelta(days=1))
    commitment.evidence_event_ids = [recent.id]

    asks = detect_gaps(nodes, edges, [recent], NOW, NOW)

    assert _by_rule(asks, "commitment_no_owner") == []


def test_commitment_without_recent_evidence_asks_for_thread() -> None:
    nodes, edges = _sponsored_baseline()
    commitment = _node("commitment", "MSA signed", evidence_event_ids=[uuid.uuid4()])
    nodes.append(commitment)
    owner = _node("stakeholder", "Priya Patel")
    nodes.append(owner)
    edges.append(_edge("owed_by", commitment, owner))

    # The cited event is outside the recency window (not in recent_events).
    asks = detect_gaps(nodes, edges, [], NOW, NOW)

    stale = _by_rule(asks, "commitment_no_recent_evidence")
    assert len(stale) == 1
    assert stale[0].target_node_id == commitment.id
    assert stale[0].remedy_kind == "forward"


def test_open_risk_without_mitigation_edge_fires_high() -> None:
    nodes, edges = _sponsored_baseline()
    risk = _node("risk", "Calibration slip", status="open")
    nodes.append(risk)

    asks = detect_gaps(nodes, edges, [], NOW, NOW)

    fired = _by_rule(asks, "risk_unmitigated")
    assert len(fired) == 1
    assert fired[0].severity == "high"
    assert fired[0].target_node_id == risk.id


def test_mitigated_or_closed_risks_stay_quiet() -> None:
    nodes, edges = _sponsored_baseline()
    mitigated = _node("risk", "Mitigated risk", status="open")
    system = _node("system", "LiDAR ingest")
    closed = _node("risk", "Closed risk", status="mitigated")
    nodes += [mitigated, system, closed]
    edges.append(_edge("blocks", mitigated, system))

    asks = detect_gaps(nodes, edges, [], NOW, NOW)

    assert _by_rule(asks, "risk_unmitigated") == []


def test_no_sponsor_fires_once_when_no_stakeholder_qualifies() -> None:
    stakeholder = _node("stakeholder", "Jordan Kim")
    asks = detect_gaps([stakeholder], [], [], NOW, NOW)

    fired = _by_rule(asks, "no_sponsor")
    assert len(fired) == 1
    assert fired[0].target_node_id is None
    assert fired[0].id == gap_ask_id("no_sponsor", None)


def test_sponsor_via_edge_or_attribute_satisfies_the_rule() -> None:
    # Attribute path (_sponsored_baseline) …
    nodes, edges = _sponsored_baseline()
    assert _by_rule(detect_gaps(nodes, edges, [], NOW, NOW), "no_sponsor") == []
    # … and edge path.
    stakeholder = _node("stakeholder", "Jordan Kim")
    decision = _node("decision", "Go decision", evidence_event_ids=[uuid.uuid4()])
    sponsors = _edge("sponsors", stakeholder, decision)
    assert _by_rule(detect_gaps([stakeholder, decision], [sponsors], [], NOW, NOW), "no_sponsor") == []


def test_no_sponsor_stays_quiet_on_an_empty_matrix() -> None:
    asks = detect_gaps([], [], [], None, NOW)
    assert _by_rule(asks, "no_sponsor") == []


def test_decision_without_evidence_asks_for_source_artifact() -> None:
    nodes, edges = _sponsored_baseline()
    bare = _node("decision", "Phase 2 rollout approved")
    cited = _node("decision", "Okta chosen", evidence_event_ids=[uuid.uuid4()])
    nodes += [bare, cited]

    asks = detect_gaps(nodes, edges, [], NOW, NOW)

    fired = _by_rule(asks, "decision_no_evidence")
    assert [a.target_node_id for a in fired] == [bare.id]
    assert fired[0].remedy_kind == "capture"


def test_engagement_silent_after_fourteen_days_or_no_events() -> None:
    nodes, edges = _sponsored_baseline()

    silent = detect_gaps(nodes, edges, [], NOW - timedelta(days=15), NOW)
    assert len(_by_rule(silent, "engagement_silent")) == 1

    never = detect_gaps(nodes, edges, [], None, NOW)
    assert len(_by_rule(never, "engagement_silent")) == 1

    active = detect_gaps(nodes, edges, [], NOW - timedelta(days=2), NOW)
    assert _by_rule(active, "engagement_silent") == []


def test_ask_ids_are_deterministic_across_recomputes() -> None:
    nodes, edges = _sponsored_baseline()
    risk = _node("risk", "Calibration slip", status="open")
    nodes.append(risk)

    first = detect_gaps(nodes, edges, [], NOW, NOW)
    second = detect_gaps(nodes, edges, [], NOW, NOW)

    assert [a.id for a in first] == [a.id for a in second]


def test_asks_sort_high_severity_first() -> None:
    nodes, edges = _sponsored_baseline()
    nodes.append(_node("risk", "Calibration slip", status="open"))
    nodes.append(_node("commitment", "MSA signed"))

    asks = detect_gaps(nodes, edges, [], NOW - timedelta(days=30), NOW)

    severities = [a.severity for a in asks]
    assert severities == sorted(severities, key=lambda s: {"high": 0, "medium": 1, "low": 2}[s])
