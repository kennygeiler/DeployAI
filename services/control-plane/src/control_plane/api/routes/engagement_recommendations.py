"""Deterministic next-action recommendations over an engagement's matrix."""

from __future__ import annotations

import hashlib
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import (
    _require_engagement,
    require_internal,
)
from control_plane.db import get_app_db_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.matrix import MatrixEdge, MatrixNode

router = APIRouter(prefix="/engagements", tags=["internal-engagements-recommendations"])

# Role + priority enums shipped through the wire.
ROLE_FDE = "fde"
ROLE_STRATEGIST = "deployment_strategist"
ROLE_BIZ_DEV = "biz_dev"

PRIORITY_HIGH = "high"
PRIORITY_MEDIUM = "medium"
PRIORITY_LOW = "low"

# Predicate thresholds.
_DECISION_STALE_DAYS = 14
_RECENT_EVENTS_DAYS = 90
_RECENT_EVENTS_CAP = 200

# Edge-type sets used by predicates.
_RISK_MITIGATION_EDGES = ("blocks", "affects")
_SYSTEM_OWNER_EDGES = ("owns",)
_OPPORTUNITY_ENABLES_EDGES = ("enables",)
# A commitment with any of these edges is considered linked (owed_by /
# owed_to / depends_on).
_COMMITMENT_LINK_EDGES = ("owed_by", "owed_to", "depends_on")

# Priority sort key so the route returns high → medium → low deterministically.
_PRIORITY_ORDER = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_LOW: 2}


class Recommendation(BaseModel):
    id: str
    role: str
    priority: str
    title: str
    body: str
    citation_node_ids: list[uuid.UUID]
    citation_edge_ids: list[uuid.UUID]


class RecommendationsResponse(BaseModel):
    recommendations: list[Recommendation]


def _rec_id(predicate: str, node_ids: tuple[uuid.UUID, ...], edge_ids: tuple[uuid.UUID, ...]) -> str:
    """Stable id per predicate-instance — same inputs → same id across calls."""
    sorted_nodes = ",".join(sorted(str(n) for n in node_ids))
    sorted_edges = ",".join(sorted(str(e) for e in edge_ids))
    blob = f"{predicate}|{sorted_nodes}|{sorted_edges}".encode()
    return hashlib.sha256(blob).hexdigest()[:16]


def _build_recommendations(
    nodes: list[MatrixNode],
    edges: list[MatrixEdge],
    recent_events: list[CanonicalMemoryEvent],
    now: datetime,
) -> list[Recommendation]:
    edges_by_from: dict[uuid.UUID, list[MatrixEdge]] = {}
    edges_by_to: dict[uuid.UUID, list[MatrixEdge]] = {}
    for e in edges:
        edges_by_from.setdefault(e.from_node_id, []).append(e)
        edges_by_to.setdefault(e.to_node_id, []).append(e)

    nodes_by_id: dict[uuid.UUID, MatrixNode] = {n.id: n for n in nodes}
    events_by_id: dict[uuid.UUID, CanonicalMemoryEvent] = {ev.id: ev for ev in recent_events}

    out: list[Recommendation] = []

    # 1) Open risk with no mitigation commitment edge → biz_dev, high.
    for n in nodes:
        if n.node_type != "risk":
            continue
        outgoing = edges_by_from.get(n.id, [])
        if any(e.edge_type in _RISK_MITIGATION_EDGES for e in outgoing):
            continue
        node_ids = (n.id,)
        edge_ids: tuple[uuid.UUID, ...] = ()
        out.append(
            Recommendation(
                id=_rec_id("risk_no_mitigation", node_ids, edge_ids),
                role=ROLE_BIZ_DEV,
                priority=PRIORITY_HIGH,
                title=f"Risk “{n.title}” has no mitigation commitment",
                body=(
                    f"Risk “{n.title}” has no mitigation commitment yet. Surface to legal/exec and capture an owner."
                ),
                citation_node_ids=list(node_ids),
                citation_edge_ids=list(edge_ids),
            )
        )

    # 2) Decision node not revisited in 14+ days → deployment_strategist, medium.
    for n in nodes:
        if n.node_type != "decision":
            continue
        cited = [events_by_id[eid] for eid in (n.evidence_event_ids or ()) if eid in events_by_id]
        most_recent = max((ev.occurred_at for ev in cited), default=None)
        if most_recent is not None and _days_since(most_recent, now) < _DECISION_STALE_DAYS:
            continue
        node_ids = (n.id,)
        edge_ids = tuple(ev.id for ev in cited)
        days_label = f"{_days_since(most_recent, now)} days" if most_recent is not None else "no recent activity"
        out.append(
            Recommendation(
                id=_rec_id("decision_stale", node_ids, ()),
                role=ROLE_STRATEGIST,
                priority=PRIORITY_MEDIUM,
                title=f"Decision “{n.title}” has not been revisited",
                body=(
                    f"Decision “{n.title}” has not been revisited in "
                    f"{_DECISION_STALE_DAYS}+ days ({days_label}). "
                    "Confirm it still stands or schedule a recheck."
                ),
                citation_node_ids=list(node_ids),
                citation_edge_ids=[],
            )
        )

    # 3) System node with no stakeholder owner edge → fde, low.
    for n in nodes:
        if n.node_type != "system":
            continue
        incoming = edges_by_to.get(n.id, [])
        has_owner = any(
            e.edge_type in _SYSTEM_OWNER_EDGES
            and nodes_by_id.get(e.from_node_id) is not None
            and nodes_by_id[e.from_node_id].node_type == "stakeholder"
            for e in incoming
        )
        if has_owner:
            continue
        node_ids = (n.id,)
        out.append(
            Recommendation(
                id=_rec_id("system_no_owner", node_ids, ()),
                role=ROLE_FDE,
                priority=PRIORITY_LOW,
                title=f"System “{n.title}” has no named owner",
                body=(
                    f"System “{n.title}” has no named owner/stakeholder. "
                    "Add an ``owns`` edge from the responsible stakeholder."
                ),
                citation_node_ids=list(node_ids),
                citation_edge_ids=[],
            )
        )

    # 4) Commitment with no link edge to who it's owed-by / owed-to / depends-on
    #    → biz_dev, medium. A floating commitment usually means we wrote it down
    #    but never said who is on the hook.
    for n in nodes:
        if n.node_type != "commitment":
            continue
        outgoing = edges_by_from.get(n.id, [])
        incoming = edges_by_to.get(n.id, [])
        related = [e for e in outgoing + incoming if e.edge_type in _COMMITMENT_LINK_EDGES]
        if related:
            continue
        node_ids = (n.id,)
        out.append(
            Recommendation(
                id=_rec_id("commitment_unlinked", node_ids, ()),
                role=ROLE_BIZ_DEV,
                priority=PRIORITY_MEDIUM,
                title=f"Commitment “{n.title}” has no counterparty",
                body=(
                    f"Commitment “{n.title}” is recorded but not linked to "
                    "who owes it or who it is owed to. Add the counterparty."
                ),
                citation_node_ids=list(node_ids),
                citation_edge_ids=[],
            )
        )

    # 5) Stakeholder with no edges at all → deployment_strategist, low.
    #    Orphan stakeholders mean we know a person matters but not how.
    for n in nodes:
        if n.node_type != "stakeholder":
            continue
        if edges_by_from.get(n.id) or edges_by_to.get(n.id):
            continue
        node_ids = (n.id,)
        out.append(
            Recommendation(
                id=_rec_id("stakeholder_orphan", node_ids, ()),
                role=ROLE_STRATEGIST,
                priority=PRIORITY_LOW,
                title=f"Stakeholder “{n.title}” is not linked to anything",
                body=(
                    f"Stakeholder “{n.title}” has no relationships on the matrix "
                    "yet. Link them to an org, a system they own, or a decision they sponsor."
                ),
                citation_node_ids=list(node_ids),
                citation_edge_ids=[],
            )
        )

    # 6) Opportunity with no ``enables`` outgoing edge → biz_dev, medium.
    #    An opportunity that doesn't enable anything is unactioned.
    for n in nodes:
        if n.node_type != "opportunity":
            continue
        outgoing = edges_by_from.get(n.id, [])
        if any(e.edge_type in _OPPORTUNITY_ENABLES_EDGES for e in outgoing):
            continue
        node_ids = (n.id,)
        out.append(
            Recommendation(
                id=_rec_id("opportunity_no_enables", node_ids, ()),
                role=ROLE_BIZ_DEV,
                priority=PRIORITY_MEDIUM,
                title=f"Opportunity “{n.title}” is not connected to an outcome",
                body=(
                    f"Opportunity “{n.title}” has no ``enables`` edge. "
                    "Connect it to the decision or system it would unlock so it can be prioritized."
                ),
                citation_node_ids=list(node_ids),
                citation_edge_ids=[],
            )
        )

    out.sort(key=lambda r: (_PRIORITY_ORDER.get(r.priority, 99), r.title))
    return out


def _days_since(moment: datetime, now: datetime) -> int:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return int((now - moment).total_seconds() // 86400)


@router.get(
    "/{engagement_id}/recommendations",
    response_model=RecommendationsResponse,
    dependencies=[Depends(require_internal)],
)
async def get_engagement_recommendations(
    engagement_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_app_db_session)],
    tenant_id: Annotated[uuid.UUID, Query()],
) -> RecommendationsResponse:
    await _require_engagement(session, tenant_id, engagement_id)
    nodes_q = await session.execute(select(MatrixNode).where(MatrixNode.engagement_id == engagement_id))
    nodes = list(nodes_q.scalars().all())
    edges_q = await session.execute(select(MatrixEdge).where(MatrixEdge.engagement_id == engagement_id))
    edges = list(edges_q.scalars().all())
    cutoff = datetime.now(UTC) - timedelta(days=_RECENT_EVENTS_DAYS)
    events_q = await session.execute(
        select(CanonicalMemoryEvent)
        .where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            CanonicalMemoryEvent.engagement_id == engagement_id,
            CanonicalMemoryEvent.occurred_at >= cutoff,
        )
        .order_by(CanonicalMemoryEvent.occurred_at.desc())
        .limit(_RECENT_EVENTS_CAP)
    )
    events = list(events_q.scalars().all())
    return RecommendationsResponse(recommendations=_build_recommendations(nodes, edges, events, datetime.now(UTC)))
