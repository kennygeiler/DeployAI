"""Structured introspection of the BlueState-XL seed (ticket G2).

The XL builder is fully deterministic (uuid5 over stable labels), which
means it *knows* every stakeholder, decision, risk and edge it seeds.
This module gives that knowledge a typed shape so downstream consumers —
chiefly the derived-ground-truth question generator in
``tests/golden/agent_kenny/derive.py`` — can enumerate seeded facts with
their real UUIDs instead of scraping the SQL text.

Purely additive: nothing here changes what the seed writes. The builder
fills an :class:`XlIntrospection` instance as a side channel while it
emits the exact same SQL it always has.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field


@dataclass(frozen=True)
class StakeholderFact:
    """One stakeholder node the seed creates (and possibly later deletes)."""

    cluster: str  # e.g. "stakeholder-vance"
    title: str  # e.g. "Patricia Vance (CMO)"
    node_id: uuid.UUID
    create_event_id: uuid.UUID
    hire_week: int
    depart_week: int | None  # None = still on the roster at week 260

    @property
    def display_name(self) -> str:
        """Person name without the parenthesised role suffix."""
        return self.title.split(" (")[0].strip()


@dataclass(frozen=True)
class DecisionFact:
    """One decision proposal thread (accepted or rejected)."""

    cluster: str  # e.g. "decision-q3-observability-27"
    title: str
    proposal_week: int
    decided_week: int  # week the accept/reject lands (>= proposal_week)
    accepted: bool
    node_id: uuid.UUID | None  # only accepted decisions materialise a node
    create_event_id: uuid.UUID
    accept_event_id: uuid.UUID | None
    reject_event_id: uuid.UUID | None


@dataclass(frozen=True)
class RiskFact:
    """One risk insight, with its resolution (if any)."""

    cluster: str
    title: str
    insight_id: uuid.UUID
    open_week: int
    open_event_id: uuid.UUID
    close_week: int | None  # None = risk never resolves in the corpus
    close_event_id: uuid.UUID | None


@dataclass(frozen=True)
class SystemFact:
    title: str
    node_id: uuid.UUID
    week: int
    create_event_id: uuid.UUID


@dataclass(frozen=True)
class CommitmentFact:
    title: str
    node_id: uuid.UUID
    week: int
    create_event_id: uuid.UUID


@dataclass(frozen=True)
class EdgeFact:
    """One matrix edge, with symbolic endpoints for template derivation.

    ``from_key`` / ``to_key`` are the builder-side identity of each
    endpoint: a stakeholder/decision *cluster* slug or a system/commitment
    *title* — whichever the endpoint kind uses as its natural key.
    """

    edge_type: str  # "sponsors" | "depends_on" | "affects"
    from_kind: str  # "stakeholder" | "decision" | "system"
    from_key: str
    to_kind: str  # "decision" | "system" | "commitment"
    to_key: str
    week: int
    edge_id: uuid.UUID
    event_id: uuid.UUID


@dataclass
class XlIntrospection:
    """Registry of every seeded fact, filled by ``build_xl_scenario_sql``."""

    stakeholders: list[StakeholderFact] = field(default_factory=list)
    decisions: list[DecisionFact] = field(default_factory=list)
    risks: list[RiskFact] = field(default_factory=list)
    systems: list[SystemFact] = field(default_factory=list)
    commitments: list[CommitmentFact] = field(default_factory=list)
    edges: list[EdgeFact] = field(default_factory=list)

    def sponsor_of(self, decision_cluster: str) -> EdgeFact | None:
        """The ``sponsors`` edge pointing at a decision, if one was seeded."""
        for e in self.edges:
            if e.edge_type == "sponsors" and e.to_key == decision_cluster:
                return e
        return None

    def dependency_of(self, decision_cluster: str) -> EdgeFact | None:
        """The decision→system ``depends_on`` edge, if one was seeded."""
        for e in self.edges:
            if e.edge_type == "depends_on" and e.from_kind == "decision" and e.from_key == decision_cluster:
                return e
        return None


def build_xl_introspection() -> XlIntrospection:
    """Build the full introspection registry without touching a database.

    Runs the SQL builder against a fixed epoch anchor (all UUIDs are
    anchor-independent — uuid5 labels never embed timestamps) and discards
    the SQL text.
    """
    from datetime import UTC, datetime

    from control_plane.scenarios.bluestate_xl.builder import XlTimeAnchor, build_xl_scenario_sql

    intro = XlIntrospection()
    anchor = XlTimeAnchor(base_now=datetime(2026, 1, 1, tzinfo=UTC))
    build_xl_scenario_sql(anchor, introspection=intro)
    return intro


__all__ = [
    "CommitmentFact",
    "DecisionFact",
    "EdgeFact",
    "RiskFact",
    "StakeholderFact",
    "SystemFact",
    "XlIntrospection",
    "build_xl_introspection",
]
