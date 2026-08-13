"""Deterministic gap detection over an engagement's matrix (Wave 5, GA1).

"Kenny asks": instead of the user guessing what to upload next, the system
detects what the decision record is *missing* and asks for it specifically.
Pure predicates over the matrix + event recency — no LLM calls; the sibling
surface is ``engagement_recommendations`` (role-addressed next actions),
while asks are evidence-addressed requests with durable dismissal.

Ask ids are deterministic hashes of (rule, target) so a dismissal recorded
in ``gap_ask_dismissals`` survives recomputes — the same gap always maps to
the same id until the underlying node is resolved or deleted.

Rules that the data model cannot support are deliberately absent:

- "commitment with no due date" — nothing in the codebase writes a due-date
  key into commitment node ``attributes`` (the only ``due_date`` in the
  system lives on strategist follow-up items). The recency variant below
  (``commitment_no_recent_evidence``) covers the same intent: a commitment
  nobody has evidenced lately needs the thread that pins it.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel

from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.matrix import MatrixEdge, MatrixNode
from control_plane.services.engagement_legibility import is_risk_open

# Remedy kinds shipped through the wire — the web maps these to CTAs.
REMEDY_CAPTURE = "capture"  # paste/upload the artifact into Capture
REMEDY_FORWARD = "forward"  # forward the email thread that answers it
REMEDY_ANSWER = "answer"  # a human knows the answer; capture it directly

SEVERITY_HIGH = "high"
SEVERITY_MEDIUM = "medium"
SEVERITY_LOW = "low"

_SEVERITY_ORDER = {SEVERITY_HIGH: 0, SEVERITY_MEDIUM: 1, SEVERITY_LOW: 2}

# An engagement with no canonical event in this many days counts as silent.
SILENCE_DAYS = 14
# A commitment none of whose evidence events occurred within this window
# has "no recent evidence" pinning it.
COMMITMENT_EVIDENCE_STALE_DAYS = 14

# Edge-type conventions (mirrors engagement_recommendations + the seeded
# scenarios): commitments name their owner via ``owed_by``; a risk with an
# outgoing ``blocks``/``affects`` edge is considered addressed; sponsorship
# is an outgoing ``sponsors`` edge or an ``is_sponsor`` node attribute
# (the oracle reads the same attribute).
_OWNER_EDGE = "owed_by"
_RISK_MITIGATION_EDGES = ("blocks", "affects")
_SPONSOR_EDGE = "sponsors"
_SPONSOR_ATTRIBUTE = "is_sponsor"


class GapAsk(BaseModel):
    """One actionable ask-card: what's missing and how to close the gap."""

    id: str
    rule: str
    severity: str
    target_node_id: uuid.UUID | None
    title: str
    why: str
    remedy_kind: str


def gap_ask_id(rule: str, target: uuid.UUID | None) -> str:
    """Stable id per (rule, target) — same gap → same id across recomputes."""
    blob = f"{rule}|{target or ''}".encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def detect_gaps(
    nodes: Sequence[MatrixNode],
    edges: Sequence[MatrixEdge],
    recent_events: Sequence[CanonicalMemoryEvent],
    latest_event_at: datetime | None,
    now: datetime,
) -> list[GapAsk]:
    """Run every gap rule over one engagement's matrix.

    ``recent_events`` is the canonical-event window used for evidence
    recency (the caller bounds it to ``COMMITMENT_EVIDENCE_STALE_DAYS``);
    ``latest_event_at`` is the engagement-wide max ``occurred_at`` so the
    silence rule sees beyond that window.
    """
    edges_by_from: dict[uuid.UUID, list[MatrixEdge]] = {}
    edges_by_to: dict[uuid.UUID, list[MatrixEdge]] = {}
    for e in edges:
        edges_by_from.setdefault(e.from_node_id, []).append(e)
        edges_by_to.setdefault(e.to_node_id, []).append(e)
    recent_event_ids = {ev.id for ev in recent_events}

    out: list[GapAsk] = []

    # 1) Commitment with no owed_by edge → nobody is named as the owner.
    for n in nodes:
        if n.node_type != "commitment":
            continue
        touching = edges_by_from.get(n.id, []) + edges_by_to.get(n.id, [])
        if any(e.edge_type == _OWNER_EDGE for e in touching):
            continue
        out.append(
            GapAsk(
                id=gap_ask_id("commitment_no_owner", n.id),
                rule="commitment_no_owner",
                severity=SEVERITY_MEDIUM,
                target_node_id=n.id,
                title=f"Who owns “{n.title}”?",
                why=f"Commitment “{n.title}” has no owed-by relationship naming who is on the hook.",
                remedy_kind=REMEDY_ANSWER,
            )
        )

    # 2) Commitment with no evidence event inside the recency window — the
    #    record says it exists but nothing recent pins it down.
    for n in nodes:
        if n.node_type != "commitment":
            continue
        if any(eid in recent_event_ids for eid in n.evidence_event_ids or ()):
            continue
        out.append(
            GapAsk(
                id=gap_ask_id("commitment_no_recent_evidence", n.id),
                rule="commitment_no_recent_evidence",
                severity=SEVERITY_LOW,
                target_node_id=n.id,
                title=f"Forward the thread that pins “{n.title}”",
                why=(
                    f"Commitment “{n.title}” has no evidence from the last "
                    f"{COMMITMENT_EVIDENCE_STALE_DAYS} days pinning it down."
                ),
                remedy_kind=REMEDY_FORWARD,
            )
        )

    # 3) Open risk with no mitigation edge (blocks/affects) → nothing on
    #    record says what's being done about it.
    for n in nodes:
        if n.node_type != "risk" or not is_risk_open(n.status):
            continue
        outgoing = edges_by_from.get(n.id, [])
        if any(e.edge_type in _RISK_MITIGATION_EDGES for e in outgoing):
            continue
        out.append(
            GapAsk(
                id=gap_ask_id("risk_unmitigated", n.id),
                rule="risk_unmitigated",
                severity=SEVERITY_HIGH,
                target_node_id=n.id,
                title=f"What is being done about “{n.title}”?",
                why=f"Risk “{n.title}” is open with no mitigation on record.",
                remedy_kind=REMEDY_ANSWER,
            )
        )

    # 4) No stakeholder marked as sponsor — fires once per engagement, and
    #    only when the matrix has content (an empty engagement gets the
    #    silence ask, not a wall of structural asks).
    if nodes and not _has_sponsor(nodes, edges_by_from):
        out.append(
            GapAsk(
                id=gap_ask_id("no_sponsor", None),
                rule="no_sponsor",
                severity=SEVERITY_HIGH,
                target_node_id=None,
                title="Who signs this deal?",
                why="No stakeholder on the matrix is marked as the sponsor or economic buyer.",
                remedy_kind=REMEDY_ANSWER,
            )
        )

    # 5) Decision with no evidence — a decision the record cannot back up.
    for n in nodes:
        if n.node_type != "decision" or (n.evidence_event_ids or []):
            continue
        out.append(
            GapAsk(
                id=gap_ask_id("decision_no_evidence", n.id),
                rule="decision_no_evidence",
                severity=SEVERITY_MEDIUM,
                target_node_id=n.id,
                title=f"Where was “{n.title}” decided?",
                why=f"Decision “{n.title}” cites no source artifact.",
                remedy_kind=REMEDY_CAPTURE,
            )
        )

    # 6) Engagement silent — no canonical event in SILENCE_DAYS.
    if latest_event_at is None or now - _as_utc(latest_event_at) > timedelta(days=SILENCE_DAYS):
        out.append(
            GapAsk(
                id=gap_ask_id("engagement_silent", None),
                rule="engagement_silent",
                severity=SEVERITY_MEDIUM,
                target_node_id=None,
                title="Forward the latest status thread",
                why=(
                    f"Nothing has landed in the record for over {SILENCE_DAYS} days"
                    if latest_event_at is not None
                    else "Nothing has landed in the record yet"
                ),
                remedy_kind=REMEDY_FORWARD,
            )
        )

    out.sort(key=lambda a: (_SEVERITY_ORDER.get(a.severity, 99), a.title))
    return out


def _has_sponsor(nodes: Sequence[MatrixNode], edges_by_from: dict[uuid.UUID, list[MatrixEdge]]) -> bool:
    for n in nodes:
        if n.node_type != "stakeholder":
            continue
        if bool((n.attributes or {}).get(_SPONSOR_ATTRIBUTE)):
            return True
        if any(e.edge_type == _SPONSOR_EDGE for e in edges_by_from.get(n.id, [])):
            return True
    return False


def _as_utc(moment: datetime) -> datetime:
    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment
