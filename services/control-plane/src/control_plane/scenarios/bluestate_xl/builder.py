"""BlueState-XL scenario SQL builder.

Procedurally expands the 5-year event corpus into the same SQL emission
pattern as the small BlueState fixture. Reuses the SQL helpers from
``bluestate.builder`` directly — they are stateless utilities and copying
them would risk drift between fixtures.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from control_plane.scenarios.bluestate.builder import (
    _delete_matrix_node_sql,
    _emit_ledger_sql,
    _matrix_edge_sql,
    _matrix_insight_sql,
    _matrix_node_sql,
    _q,
)
from control_plane.scenarios.bluestate_xl.events import (
    DECISIONS,
    EXTRACTOR_NOISE,
    NARRATIVE,
    RISKS_CLOSED,
    RISKS_OPENED,
    STAKEHOLDERS,
    TOTAL_WEEKS,
)
from control_plane.scenarios.bluestate_xl.introspect import (
    CommitmentFact,
    DecisionFact,
    EdgeFact,
    RiskFact,
    StakeholderFact,
    SystemFact,
    XlIntrospection,
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"
USER_STRATEGIST_ID = "aaaaaaa1-1111-4111-8111-111111111111"
USER_FDE_ID = "aaaaaaa2-2222-4222-8222-222222222222"
USER_BIZDEV_ID = "aaaaaaa3-3333-4333-8333-333333333333"
TENANT_NAME = "acme-county-pilot"

ENGAGEMENT_ID = "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"
ENGAGEMENT_NAME = "BlueState Health — Long-Cycle 5-Year Engagement"
CUSTOMER_ACCOUNT = "BlueState Health"
ENGAGEMENT_PHASE = "renewal"

TRAILING_SILENCE_DAYS = 21

_NS = uuid.UUID("88888888-1234-5678-9abc-eeeeeeeeeeee")


def _det_id(label: str) -> uuid.UUID:
    return uuid.uuid5(_NS, label)


@dataclass
class XlTimeAnchor:
    """Anchor that resolves (week, day, hour) into a real UTC datetime.

    Mirrors ``bluestate.builder.TimeAnchor`` but parametrised on 260 weeks so
    the W260 endpoint sits the same 21 days before ``base_now`` as the small
    fixture's W26.
    """

    base_now: datetime

    @property
    def end_of_program(self) -> datetime:
        return self.base_now - timedelta(days=TRAILING_SILENCE_DAYS)

    @property
    def w1_monday(self) -> datetime:
        return self.end_of_program - timedelta(days=(TOTAL_WEEKS - 1) * 7 + 6)

    def at(self, week: int, day: int, hour: int) -> datetime:
        offset = timedelta(weeks=week - 1, days=day - 1, hours=hour - 9)
        return self.w1_monday + offset


def build_xl_scenario_sql(
    anchor: XlTimeAnchor,
    *,
    introspection: XlIntrospection | None = None,
    max_week: int | None = None,
) -> tuple[str, dict[str, dict[str, uuid.UUID]]]:
    """Construct the full multi-statement SQL block for BlueState-XL.

    ``introspection`` is an optional side channel (ticket G2): when
    supplied, the builder records a typed fact for every stakeholder /
    decision / risk / system / commitment / edge it emits — same UUIDs,
    same weeks — without altering the SQL output in any way.

    ``max_week`` is the explicit progressive mode (ticket G3): only events
    whose timeline week is ``<= max_week`` are emitted, producing the true
    prefix of the engagement — risks not yet closed stay open, stakeholders
    not yet departed stay on the roster. Every emitted row keeps the exact
    UUID it has in the full corpus (loops keep full-list enumeration so
    idx-derived labels never shift), which is what makes longitudinal
    checkpoints comparable. ``None`` (default) seeds all 260 weeks —
    byte-identical to the pre-G3 output.
    """
    if max_week is not None and not 1 <= max_week <= TOTAL_WEEKS:
        raise ValueError(f"max_week must be in 1..{TOTAL_WEEKS}; got {max_week}")

    def _beyond(week: int) -> bool:
        return max_week is not None and week > max_week

    statements: list[str] = ["BEGIN;"]
    registry: dict[str, dict[str, uuid.UUID]] = {}

    # Introspection staging (assembled into facts at the end of the walk,
    # once departure / closure weeks are known).
    _stake_meta: dict[str, tuple[str, uuid.UUID, uuid.UUID, int]] = {}
    _stake_departs: dict[str, int] = {}
    _risk_open_meta: dict[str, tuple[str, uuid.UUID, int, uuid.UUID]] = {}
    _risk_close_meta: dict[str, tuple[int, uuid.UUID]] = {}

    cluster_to_event_id: dict[str, uuid.UUID] = {}
    for ev in NARRATIVE:
        if _beyond(ev.week):
            continue
        event_id = _det_id(f"xl-narrative|{ev.cluster}")
        cluster_to_event_id[ev.cluster or ""] = event_id
        occurred_at = anchor.at(ev.week, ev.day, ev.hour)
        statements.append(
            _emit_ledger_sql(
                event_id=event_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=occurred_at,
                actor_kind=ev.actor_kind,
                actor_id=None,
                source_kind=ev.kind,
                source_ref=None,
                summary=ev.summary,
                detail_json='{"body_excerpt": "' + _q(ev.body[:200].replace("\n", " ")) + '"}',
            )
        )

    stakeholder_node_ids: dict[str, uuid.UUID] = {}
    for ev in STAKEHOLDERS:
        if _beyond(ev.week):
            continue
        occurred_at = anchor.at(ev.week, ev.day, ev.hour)
        if ev.kind == "matrix_node_created":
            node_id = _det_id(f"xl-stakeholder-node|{ev.cluster}")
            stakeholder_node_ids[ev.cluster or ""] = node_id
            event_id = _det_id(f"xl-stakeholder-evt|{ev.cluster}|create")
            evidence: list[uuid.UUID] = [event_id]
            for nev in NARRATIVE[:200]:
                if nev.week == ev.week and nev.cluster in cluster_to_event_id:
                    nid = cluster_to_event_id[nev.cluster]
                    if nid not in evidence:
                        evidence.append(nid)
                    if len(evidence) >= 5:
                        break
            statements.append(
                _matrix_node_sql(
                    node_id=node_id,
                    tenant_id=TENANT_ID,
                    engagement_id=ENGAGEMENT_ID,
                    node_type="stakeholder",
                    title=ev.title or "stakeholder",
                    created_at=occurred_at,
                    evidence_event_ids=evidence,
                )
            )
            statements.append(
                _emit_ledger_sql(
                    event_id=event_id,
                    tenant_id=TENANT_ID,
                    engagement_id=ENGAGEMENT_ID,
                    occurred_at=occurred_at,
                    actor_kind="user",
                    actor_id="sarah.chen@deployai.com",
                    source_kind="matrix_node_created",
                    source_ref=node_id,
                    summary=ev.summary,
                    detail_json='{"node_type": "stakeholder", "title": "' + _q(ev.title or "") + '"}',
                    affects=[("matrix_node", node_id)],
                )
            )
            _stake_meta[ev.cluster or ""] = (ev.title or "stakeholder", node_id, event_id, ev.week)
        elif ev.kind == "matrix_node_deleted":
            base_lookup = (ev.cluster or "").removesuffix("-out")
            node_id = stakeholder_node_ids.get(
                base_lookup,
                _det_id(f"xl-stakeholder-node|{base_lookup}"),
            )
            event_id = _det_id(f"xl-stakeholder-evt|{ev.cluster}|delete")
            statements.append(_delete_matrix_node_sql(node_id))
            statements.append(
                _emit_ledger_sql(
                    event_id=event_id,
                    tenant_id=TENANT_ID,
                    engagement_id=ENGAGEMENT_ID,
                    occurred_at=occurred_at,
                    actor_kind="user",
                    actor_id="sarah.chen@deployai.com",
                    source_kind="matrix_node_deleted",
                    source_ref=node_id,
                    summary=ev.summary,
                    detail_json='{"node_type": "stakeholder", "title": "' + _q(ev.title or "") + '"}',
                )
            )
            _stake_departs[base_lookup] = ev.week

    decision_node_ids: dict[str, uuid.UUID] = {}
    accept_ledger_ids: dict[str, uuid.UUID] = {}
    for ev in DECISIONS:
        if _beyond(ev.week):
            continue
        proposal_id = _det_id(f"xl-decision-proposal|{ev.cluster}")
        node_id = _det_id(f"xl-decision-node|{ev.cluster}")
        created_at = anchor.at(ev.week, ev.day, ev.hour)
        if ev.week <= 8:
            cycle_hours = 24
        elif ev.week <= 52:
            cycle_hours = 72
        elif ev.week <= 156:
            cycle_hours = 120
        else:
            cycle_hours = 96
        decided_at = created_at + timedelta(hours=cycle_hours)
        # Week the accept/reject event lands in (1-based, aligned with
        # ``anchor.at``'s hour-9 Monday origin). Introspection only.
        decided_week = ((ev.week - 1) * 168 + (ev.day - 1) * 24 + (ev.hour - 9) + cycle_hours) // 168 + 1
        accept_evt_for_fact: uuid.UUID | None = None
        reject_evt_for_fact: uuid.UUID | None = None

        create_evt_id = _det_id(f"xl-decision-create-evt|{ev.cluster}")
        statements.append(
            _emit_ledger_sql(
                event_id=create_evt_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=created_at,
                actor_kind="agent:matrix_extractor",
                actor_id="cartographer",
                source_kind="llm_proposal_created",
                source_ref=proposal_id,
                summary=f"proposal drafted: decision — {ev.title or ev.summary}"[:500],
                detail_json='{"proposal_kind": "node", "node_type": "decision", "title": "' + _q(ev.title or "") + '"}',
            )
        )

        if ev.accept_decision:
            accept_evt_id = _det_id(f"xl-decision-accept-evt|{ev.cluster}")
            decision_evidence: list[uuid.UUID] = [create_evt_id, accept_evt_id]
            statements.append(
                _matrix_node_sql(
                    node_id=node_id,
                    tenant_id=TENANT_ID,
                    engagement_id=ENGAGEMENT_ID,
                    node_type="decision",
                    title=ev.title or ev.summary,
                    created_at=decided_at,
                    evidence_event_ids=decision_evidence,
                )
            )
            decision_node_ids[ev.cluster or ""] = node_id
            accept_ledger_ids[ev.cluster or ""] = accept_evt_id
            accept_evt_for_fact = accept_evt_id
            statements.append(
                _emit_ledger_sql(
                    event_id=accept_evt_id,
                    tenant_id=TENANT_ID,
                    engagement_id=ENGAGEMENT_ID,
                    occurred_at=decided_at,
                    actor_kind="user",
                    actor_id="sarah.chen@deployai.com",
                    source_kind="proposal_accepted",
                    source_ref=proposal_id,
                    summary=f"proposal accepted: decision — {ev.title or ''}"[:500],
                    detail_json='{"proposal_kind": "node", "node_type": "decision", "result_node_id": "'
                    + str(node_id)
                    + '"}',
                    caused_by=[create_evt_id],
                    affects=[("matrix_node", node_id)],
                )
            )
        elif ev.rejects_acceptance:
            reject_evt_id = _det_id(f"xl-decision-reject-evt|{ev.cluster}")
            reject_evt_for_fact = reject_evt_id
            statements.append(
                _emit_ledger_sql(
                    event_id=reject_evt_id,
                    tenant_id=TENANT_ID,
                    engagement_id=ENGAGEMENT_ID,
                    occurred_at=decided_at,
                    actor_kind="user",
                    actor_id="sarah.chen@deployai.com",
                    source_kind="proposal_rejected",
                    source_ref=proposal_id,
                    summary=f"proposal rejected: decision — {ev.title or ''}"[:500],
                    detail_json='{"proposal_kind": "node", "node_type": "decision"}',
                    caused_by=[create_evt_id],
                )
            )
        if introspection is not None:
            introspection.decisions.append(
                DecisionFact(
                    cluster=ev.cluster or "",
                    title=ev.title or ev.summary,
                    proposal_week=ev.week,
                    decided_week=decided_week,
                    accepted=ev.accept_decision,
                    node_id=node_id if ev.accept_decision else None,
                    create_event_id=create_evt_id,
                    accept_event_id=accept_evt_for_fact,
                    reject_event_id=reject_evt_for_fact,
                )
            )

    for ev in EXTRACTOR_NOISE:
        if _beyond(ev.week):
            continue
        proposal_id = _det_id(f"xl-extractor-noise-proposal|{ev.cluster}")
        created_at = anchor.at(ev.week, ev.day, ev.hour)
        decided_at = created_at + timedelta(hours=6)
        create_evt_id = _det_id(f"xl-extractor-noise-create-evt|{ev.cluster}")
        statements.append(
            _emit_ledger_sql(
                event_id=create_evt_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=created_at,
                actor_kind="agent:matrix_extractor",
                actor_id="cartographer",
                source_kind="llm_proposal_created",
                source_ref=proposal_id,
                summary=f"proposal drafted: {ev.title or ev.summary}"[:500],
                detail_json='{"proposal_kind": "node", "node_type": "system"}',
            )
        )
        accept_evt_id = _det_id(f"xl-extractor-noise-accept-evt|{ev.cluster}")
        statements.append(
            _emit_ledger_sql(
                event_id=accept_evt_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=decided_at,
                actor_kind="user",
                actor_id="marcus.rivera@deployai.com",
                source_kind="proposal_accepted",
                source_ref=proposal_id,
                summary=f"proposal accepted: {ev.title or ev.summary}"[:500],
                detail_json='{"proposal_kind": "node", "node_type": "system"}',
                caused_by=[create_evt_id],
            )
        )

    risk_insight_ids: dict[str, uuid.UUID] = {}
    for ev in RISKS_OPENED:
        if _beyond(ev.week):
            continue
        opened_at = anchor.at(ev.week, ev.day, ev.hour)
        insight_id = _det_id(f"xl-risk-insight|{ev.cluster}")
        risk_insight_ids[ev.cluster or ""] = insight_id
        statements.append(
            _matrix_insight_sql(
                insight_id=insight_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                title=ev.title or ev.summary,
                body=ev.body,
                severity="medium",
                created_at=opened_at,
            )
        )
        open_evt_id = _det_id(f"xl-risk-open-evt|{ev.cluster}")
        statements.append(
            _emit_ledger_sql(
                event_id=open_evt_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=opened_at,
                actor_kind="agent:oracle",
                actor_id="oracle",
                source_kind="insight_opened",
                source_ref=insight_id,
                summary=f"risk opened: {ev.title or ev.summary}"[:500],
                detail_json='{"node_type": "risk", "insight_type": "risk", "severity": "medium", "agent": "oracle"}',
                affects=[("insight", insight_id)],
            )
        )
        _risk_open_meta[ev.cluster or ""] = (ev.title or ev.summary, insight_id, ev.week, open_evt_id)

    for ev in RISKS_CLOSED:
        if _beyond(ev.week):
            # Progressive prefix: a close beyond the horizon simply hasn't
            # happened yet — the risk stays open, which is the honest state.
            continue
        closed_at = anchor.at(ev.week, ev.day, ev.hour)
        insight_id = risk_insight_ids.get(
            ev.risk_close_of or "",
            _det_id(f"xl-risk-insight|{ev.risk_close_of}"),
        )
        close_evt_id = _det_id(f"xl-risk-close-evt|{ev.risk_close_of}")
        statements.append(
            f"UPDATE matrix_insights SET status = 'resolved', "
            f"decided_at = '{closed_at.isoformat()}'::timestamptz, decided_by = 'auto' "
            f"WHERE id = '{insight_id}'::uuid;\n"
        )
        statements.append(
            _emit_ledger_sql(
                event_id=close_evt_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=closed_at,
                actor_kind="system",
                actor_id="auto",
                source_kind="insight_closed",
                source_ref=insight_id,
                summary=f"risk closed: {ev.title or ev.summary}"[:500],
                detail_json=(
                    '{"node_type": "risk", "insight_type": "risk", "severity": "medium",'
                    ' "agent": "oracle", "status": "resolved"}'
                ),
                affects=[("insight", insight_id)],
            )
        )
        _risk_close_meta[ev.risk_close_of or ""] = (ev.week, close_evt_id)

    system_titles = [
        ("Member Portal (web)", 1),
        ("Eligibility Service (mainframe)", 1),
        ("Claims API (Oracle)", 1),
        ("Provider Directory API (HealthwayDirect)", 1),
        ("Member Identity (Okta)", 1),
        ("In-portal Messaging Subsystem", 1),
        ("Mobile Member App (iOS/Android)", 80),
        ("Pharmacy Integration Gateway", 130),
        ("Care Coordination Hub", 180),
        ("Renewal Workflow Engine", 230),
    ]
    system_node_ids: dict[str, uuid.UUID] = {}
    for title, week in system_titles:
        node_id = _det_id(f"xl-system-node|{title}")
        system_node_ids[title] = node_id
        if _beyond(week):
            continue
        created_at = anchor.at(week, 1, 9)
        evt_id = _det_id(f"xl-system-evt|{title}")
        statements.append(
            _matrix_node_sql(
                node_id=node_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                node_type="system",
                title=title,
                created_at=created_at,
                evidence_event_ids=[evt_id],
            )
        )
        statements.append(
            _emit_ledger_sql(
                event_id=evt_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=created_at,
                actor_kind="user",
                actor_id="marcus.rivera@deployai.com",
                source_kind="matrix_node_created",
                source_ref=node_id,
                summary=f"system node added: {title}"[:500],
                detail_json='{"node_type": "system", "title": "' + _q(title) + '"}',
                affects=[("matrix_node", node_id)],
            )
        )
        if introspection is not None:
            introspection.systems.append(SystemFact(title=title, node_id=node_id, week=week, create_event_id=evt_id))

    commitments = [
        ("MSA + BAA signed", 8),
        ("Pilot launch by W24", 24),
        ("V1 GA launch by W52", 52),
        ("Y2 expansion KPI", 104),
        ("Y3 stabilisation milestone", 156),
        ("Y4 optimisation milestone", 208),
        ("Y5 renewal milestone", 256),
    ]
    commitment_node_ids: dict[str, uuid.UUID] = {}
    for title, week in commitments:
        node_id = _det_id(f"xl-commit-node|{title}")
        commitment_node_ids[title] = node_id
        if _beyond(week):
            continue
        created_at = anchor.at(week, 1, 10)
        evt_id = _det_id(f"xl-commit-evt|{title}")
        statements.append(
            _matrix_node_sql(
                node_id=node_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                node_type="commitment",
                title=title,
                created_at=created_at,
                evidence_event_ids=[evt_id],
            )
        )
        statements.append(
            _emit_ledger_sql(
                event_id=evt_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=created_at,
                actor_kind="user",
                actor_id="jamie.park@deployai.com",
                source_kind="matrix_node_created",
                source_ref=node_id,
                summary=f"commitment node added: {title}"[:500],
                detail_json='{"node_type": "commitment", "title": "' + _q(title) + '"}',
                affects=[("matrix_node", node_id)],
            )
        )
        if introspection is not None:
            introspection.commitments.append(
                CommitmentFact(title=title, node_id=node_id, week=week, create_event_id=evt_id)
            )

    # Edges: build enough to clear the ~600 target. Spread across the
    # accepted-decision set, the system catalog and the stakeholder roster
    # so the graph isn't a single star.
    #
    # Pre-compute per-cluster hire/depart weeks so edges only reference
    # stakeholders still alive at the edge timestamp; otherwise a depart
    # event (matrix_node_deleted → DELETE FROM matrix_nodes) leaves edges
    # with a dangling from_node_id and the FK fires.
    hire_week: dict[str, int] = {}
    depart_week: dict[str, int] = {}
    for ev in STAKEHOLDERS:
        if not ev.cluster:
            continue
        if ev.kind == "matrix_node_created":
            hire_week[ev.cluster] = ev.week
        elif ev.kind == "matrix_node_deleted":
            base = ev.cluster.removesuffix("-out")
            depart_week[base] = ev.week

    def _alive_clusters_at(week: int) -> list[str]:
        """Stakeholders that exist at ``week`` AND are not deleted later.

        Edges are emitted in one batch after all stakeholder create/delete
        statements, so the SQL script's final state is what the FK sees —
        any cluster that gets a ``matrix_node_deleted`` is unusable as an
        edge endpoint regardless of when in the timeline the edge belongs.
        """
        out_clusters: list[str] = []
        for cluster, hired in hire_week.items():
            if hired > week:
                continue
            if cluster in depart_week:
                continue
            out_clusters.append(cluster)
        return out_clusters

    accepted_decisions = [ev for ev in DECISIONS if ev.accept_decision]
    edges_emitted = 0
    edge_budget = 620
    system_titles_only = [t for t, _ in system_titles]
    commitment_titles_only = [t for t, _ in commitments]
    system_week_by_title = dict(system_titles)
    commitment_week_by_title = dict(commitments)

    def _add_edge(
        kind: str,
        src: uuid.UUID,
        dst: uuid.UUID,
        week: int,
        label: str,
        *,
        endpoints: tuple[str, str, str, str] | None = None,
    ) -> None:
        nonlocal edges_emitted
        edge_id = _det_id(f"xl-edge|{label}|{kind}")
        edge_evt_id = _det_id(f"xl-edge-evt|{label}|{kind}")
        edge_at = anchor.at(min(max(week, 1), TOTAL_WEEKS), 1, 9)
        if introspection is not None and endpoints is not None:
            from_kind, from_key, to_kind, to_key = endpoints
            introspection.edges.append(
                EdgeFact(
                    edge_type=kind,
                    from_kind=from_kind,
                    from_key=from_key,
                    to_kind=to_kind,
                    to_key=to_key,
                    week=min(max(week, 1), TOTAL_WEEKS),
                    edge_id=edge_id,
                    event_id=edge_evt_id,
                )
            )
        statements.append(
            _matrix_edge_sql(
                edge_id=edge_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                edge_type=kind,
                from_node_id=src,
                to_node_id=dst,
                created_at=edge_at,
            )
        )
        statements.append(
            _emit_ledger_sql(
                event_id=edge_evt_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=edge_at,
                actor_kind="user",
                actor_id="sarah.chen@deployai.com",
                source_kind="matrix_edge_created",
                source_ref=edge_id,
                summary=f"edge: {kind} ({label})"[:500],
                detail_json='{"edge_type": "' + kind + '"}',
                affects=[("matrix_edge", edge_id)],
            )
        )
        edges_emitted += 1

    # NOTE (G3): enumeration stays over the FULL accepted list even in
    # progressive mode — the idx baked into each edge label must not shift
    # with the horizon, or checkpoint corpora would stop being prefixes.
    for idx, ev in enumerate(accepted_decisions):
        if edges_emitted >= edge_budget:
            break
        if _beyond(ev.week):
            continue
        decision_id = decision_node_ids[ev.cluster or ""]
        alive_now = _alive_clusters_at(ev.week)
        if not alive_now:
            continue
        sponsor_cluster = alive_now[idx % len(alive_now)]
        sponsor_id = stakeholder_node_ids[sponsor_cluster]
        _add_edge(
            "sponsors",
            sponsor_id,
            decision_id,
            ev.week,
            f"xl-sponsor-{idx}-{ev.cluster}",
            endpoints=("stakeholder", sponsor_cluster, "decision", ev.cluster or ""),
        )
        if edges_emitted >= edge_budget:
            break
        sys_title = system_titles_only[idx % len(system_titles_only)]
        if not _beyond(system_week_by_title[sys_title]):
            _add_edge(
                "depends_on",
                decision_id,
                system_node_ids[sys_title],
                ev.week,
                f"xl-dep-{idx}-{ev.cluster}",
                endpoints=("decision", ev.cluster or "", "system", sys_title),
            )
        if edges_emitted >= edge_budget:
            break
        commit_title = commitment_titles_only[idx % len(commitment_titles_only)]
        if not _beyond(commitment_week_by_title[commit_title]):
            _add_edge(
                "affects",
                decision_id,
                commitment_node_ids[commit_title],
                ev.week,
                f"xl-affect-{idx}-{ev.cluster}",
                endpoints=("decision", ev.cluster or "", "commitment", commit_title),
            )

    # Static structural edges between systems and stakeholders to add depth.
    structural_targets = [
        ("Member Portal (web)", "Eligibility Service (mainframe)"),
        ("Member Portal (web)", "Claims API (Oracle)"),
        ("Member Portal (web)", "Member Identity (Okta)"),
        ("Mobile Member App (iOS/Android)", "Member Portal (web)"),
        ("Pharmacy Integration Gateway", "Claims API (Oracle)"),
        ("Care Coordination Hub", "Provider Directory API (HealthwayDirect)"),
        ("Renewal Workflow Engine", "Member Portal (web)"),
        ("In-portal Messaging Subsystem", "Member Portal (web)"),
    ]
    for idx, (src_title, dst_title) in enumerate(structural_targets):
        if edges_emitted >= edge_budget:
            break
        structural_week = min(1 + idx * 30, TOTAL_WEEKS)
        if (
            _beyond(structural_week)
            or _beyond(system_week_by_title[src_title])
            or _beyond(system_week_by_title[dst_title])
        ):
            continue
        _add_edge(
            "depends_on",
            system_node_ids[src_title],
            system_node_ids[dst_title],
            structural_week,
            f"xl-structural-{idx}-{src_title}-{dst_title}",
            endpoints=("system", src_title, "system", dst_title),
        )

    for user_id, role in (
        (USER_STRATEGIST_ID, "deployment_strategist"),
        (USER_FDE_ID, "fde"),
        (USER_BIZDEV_ID, "biz_dev"),
    ):
        evt_id = _det_id(f"xl-member-add|{user_id}|{role}")
        added_at = anchor.at(1, 1, 8)
        statements.append(
            _emit_ledger_sql(
                event_id=evt_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=added_at,
                actor_kind="user",
                actor_id="jamie.park@deployai.com",
                source_kind="member_added",
                source_ref=uuid.UUID(user_id),
                summary=f"engagement member added: {role}",
                detail_json='{"role": "' + role + '"}',
            )
        )

    statements.append("COMMIT;")

    if introspection is not None:
        for cluster, (title, node_id, event_id, hired) in _stake_meta.items():
            introspection.stakeholders.append(
                StakeholderFact(
                    cluster=cluster,
                    title=title,
                    node_id=node_id,
                    create_event_id=event_id,
                    hire_week=hired,
                    depart_week=_stake_departs.get(cluster),
                )
            )
        for cluster, (title, insight_id, opened, open_evt) in _risk_open_meta.items():
            close = _risk_close_meta.get(cluster)
            introspection.risks.append(
                RiskFact(
                    cluster=cluster,
                    title=title,
                    insight_id=insight_id,
                    open_week=opened,
                    open_event_id=open_evt,
                    close_week=close[0] if close else None,
                    close_event_id=close[1] if close else None,
                )
            )

    registry["clusters"] = cluster_to_event_id
    registry["stakeholders"] = stakeholder_node_ids
    registry["decisions"] = decision_node_ids
    registry["accept_ledger"] = accept_ledger_ids
    registry["risks"] = risk_insight_ids

    return "\n".join(statements), registry


__all__ = [
    "CUSTOMER_ACCOUNT",
    "ENGAGEMENT_ID",
    "ENGAGEMENT_NAME",
    "ENGAGEMENT_PHASE",
    "TENANT_ID",
    "TENANT_NAME",
    "USER_BIZDEV_ID",
    "USER_FDE_ID",
    "USER_STRATEGIST_ID",
    "XlTimeAnchor",
    "build_xl_scenario_sql",
]
