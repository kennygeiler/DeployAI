"""BlueState scenario SQL builders.

Pure data → SQL transforms. Takes a ``TimeAnchor`` and emits one large SQL
script that populates ledger_events, matrix_nodes/edges, matrix_insights for
the 26-week BlueState narrative. No I/O; the caller decides where to execute.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from control_plane.scenarios.bluestate.events import (
    DECISIONS,
    EXTRACTOR_NOISE,
    NARRATIVE,
    RISKS_CLOSED,
    RISKS_OPENED,
    STAKEHOLDERS,
)

# Stable UUIDs shared with `infra/compose/seed/seed_app.py` so a single team
# owns both the BlueState and Acme engagements.
TENANT_ID = "11111111-1111-1111-1111-111111111111"
USER_STRATEGIST_ID = "aaaaaaa1-1111-4111-8111-111111111111"
USER_FDE_ID = "aaaaaaa2-2222-4222-8222-222222222222"
USER_BIZDEV_ID = "aaaaaaa3-3333-4333-8333-333333333333"
TENANT_NAME = "acme-county-pilot"

ENGAGEMENT_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
ENGAGEMENT_NAME = "BlueState Health — Member Portal Replatform"
CUSTOMER_ACCOUNT = "BlueState Health"
ENGAGEMENT_PHASE = "build"

# W26 ends 21 days before "now" so the trailing 14d wall-clock window is
# reliably event-free for engagement_silence.
TRAILING_SILENCE_DAYS = 21


@dataclass
class TimeAnchor:
    """Anchor that resolves (week, day, hour) into a real UTC datetime."""

    base_now: datetime

    @property
    def w26_end(self) -> datetime:
        return self.base_now - timedelta(days=TRAILING_SILENCE_DAYS)

    @property
    def w1_monday(self) -> datetime:
        return self.w26_end - timedelta(days=25 * 7 + 6)

    def at(self, week: int, day: int, hour: int) -> datetime:
        offset = timedelta(weeks=week - 1, days=day - 1, hours=hour - 9)
        return self.w1_monday + offset


def _q(s: str) -> str:
    return s.replace("'", "''")


def _emit_ledger_sql(
    *,
    event_id: uuid.UUID,
    tenant_id: str,
    engagement_id: str,
    occurred_at: datetime,
    actor_kind: str,
    actor_id: str | None,
    source_kind: str,
    source_ref: uuid.UUID | None,
    summary: str,
    detail_json: str,
    caused_by: list[uuid.UUID] | None = None,
    affects: list[tuple[str, uuid.UUID]] | None = None,
) -> str:
    actor_id_sql = f"'{_q(actor_id)}'" if actor_id else "NULL"
    source_ref_sql = f"'{source_ref}'::uuid" if source_ref else "NULL"
    parts = [
        f"""INSERT INTO ledger_events
  (id, tenant_id, engagement_id, occurred_at, actor_kind, actor_id, source_kind, source_ref, summary, detail)
VALUES
  ('{event_id}'::uuid, '{tenant_id}'::uuid, '{engagement_id}'::uuid,
   '{occurred_at.isoformat()}'::timestamptz,
   '{_q(actor_kind)}', {actor_id_sql},
   '{_q(source_kind)}', {source_ref_sql},
   '{_q(summary[:500])}',
   '{_q(detail_json)}'::jsonb)
ON CONFLICT (id) DO NOTHING;"""
    ]
    for parent_id in caused_by or []:
        if parent_id == event_id:
            continue
        parts.append(
            f"INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES "
            f"('{event_id}'::uuid, '{parent_id}'::uuid) ON CONFLICT DO NOTHING;"
        )
    for entity_kind, entity_id in affects or []:
        parts.append(
            f"INSERT INTO ledger_event_affects (event_id, entity_kind, entity_id) VALUES "
            f"('{event_id}'::uuid, '{_q(entity_kind)}', '{entity_id}'::uuid) "
            f"ON CONFLICT DO NOTHING;"
        )
    return "\n".join(parts)


def _matrix_node_sql(
    *,
    node_id: uuid.UUID,
    tenant_id: str,
    engagement_id: str,
    node_type: str,
    title: str,
    created_at: datetime,
    evidence_event_ids: list[uuid.UUID] | None = None,
) -> str:
    evidence_array = (
        "ARRAY[" + ",".join(f"'{e}'::uuid" for e in evidence_event_ids) + "]::uuid[]"
        if evidence_event_ids
        else "'{}'::uuid[]"
    )
    return f"""INSERT INTO matrix_nodes
  (id, tenant_id, engagement_id, node_type, title, attributes, evidence_event_ids, created_at, updated_at)
VALUES
  ('{node_id}'::uuid, '{tenant_id}'::uuid, '{engagement_id}'::uuid,
   '{_q(node_type)}', '{_q(title[:500])}', '{{}}'::jsonb,
   {evidence_array},
   '{created_at.isoformat()}'::timestamptz, '{created_at.isoformat()}'::timestamptz)
ON CONFLICT (id) DO NOTHING;
"""


def _delete_matrix_node_sql(node_id: uuid.UUID) -> str:
    return f"DELETE FROM matrix_nodes WHERE id = '{node_id}'::uuid;\n"


def _matrix_edge_sql(
    *,
    edge_id: uuid.UUID,
    tenant_id: str,
    engagement_id: str,
    edge_type: str,
    from_node_id: uuid.UUID,
    to_node_id: uuid.UUID,
    created_at: datetime,
) -> str:
    return f"""INSERT INTO matrix_edges
  (id, tenant_id, engagement_id, edge_type, from_node_id, to_node_id,
   attributes, evidence_event_ids, created_at, updated_at)
VALUES
  ('{edge_id}'::uuid, '{tenant_id}'::uuid, '{engagement_id}'::uuid,
   '{_q(edge_type)}', '{from_node_id}'::uuid, '{to_node_id}'::uuid,
   '{{}}'::jsonb, '{{}}'::uuid[],
   '{created_at.isoformat()}'::timestamptz, '{created_at.isoformat()}'::timestamptz)
ON CONFLICT (id) DO NOTHING;
"""


def _matrix_insight_sql(
    *,
    insight_id: uuid.UUID,
    tenant_id: str,
    engagement_id: str,
    title: str,
    body: str,
    severity: str,
    created_at: datetime,
    status: str = "open",
    decided_at: datetime | None = None,
) -> str:
    decided_sql = f"'{decided_at.isoformat()}'::timestamptz" if decided_at else "NULL"
    decided_by_sql = "'auto'" if decided_at else "NULL"
    dedup = f"bluestate-{insight_id.hex[:16]}"
    input_hash = uuid.uuid5(uuid.NAMESPACE_DNS, str(insight_id)).hex
    return f"""INSERT INTO matrix_insights
  (id, tenant_id, engagement_id, agent, insight_type, severity, title, body,
   citation_node_ids, citation_edge_ids, citation_event_ids,
   dedup_key, input_hash, status, decided_at, decided_by, created_at)
VALUES
  ('{insight_id}'::uuid, '{tenant_id}'::uuid, '{engagement_id}'::uuid,
   'oracle', 'risk', '{_q(severity)}',
   '{_q(title[:500])}', '{_q(body[:5000])}',
   '{{}}'::uuid[], '{{}}'::uuid[], '{{}}'::uuid[],
   '{_q(dedup)}', '{_q(input_hash)}',
   '{_q(status)}', {decided_sql}, {decided_by_sql},
   '{created_at.isoformat()}'::timestamptz)
ON CONFLICT (id) DO NOTHING;
"""


def build_scenario_sql(
    anchor: TimeAnchor,
) -> tuple[str, dict[str, dict[str, uuid.UUID]]]:
    """Construct the full multi-statement SQL block for the scenario.

    Returns ``(sql, registry)`` where ``registry`` maps cluster IDs to the
    UUIDs they produced.
    """
    statements: list[str] = ["BEGIN;"]
    registry: dict[str, dict[str, uuid.UUID]] = {}

    ns = uuid.UUID("88888888-1234-5678-9abc-bbbbbbbbbbbb")

    def det_id(label: str) -> uuid.UUID:
        return uuid.uuid5(ns, label)

    cluster_to_event_id: dict[str, uuid.UUID] = {}
    for ev in NARRATIVE:
        event_id = det_id(f"narrative|{ev.cluster}")
        cluster_to_event_id[ev.cluster or ""] = event_id
        occurred_at = anchor.at(ev.week, ev.day, ev.hour)
        actor_id = "marcus.rivera@deployai.com" if "marcus" in ev.body.lower()[:200] else None
        statements.append(
            _emit_ledger_sql(
                event_id=event_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                occurred_at=occurred_at,
                actor_kind=ev.actor_kind,
                actor_id=actor_id,
                source_kind=ev.kind,
                source_ref=None,
                summary=ev.summary,
                detail_json='{"body_excerpt": "' + _q(ev.body[:200].replace("\n", " ")) + '"}',
            )
        )

    stakeholder_node_ids: dict[str, uuid.UUID] = {}
    for ev in STAKEHOLDERS:
        occurred_at = anchor.at(ev.week, ev.day, ev.hour)
        if ev.kind == "matrix_node_created":
            node_id = det_id(f"stakeholder-node|{ev.cluster}")
            stakeholder_node_ids[ev.cluster or ""] = node_id
            event_id = det_id(f"stakeholder-evt|{ev.cluster}|create")
            statements.append(
                _matrix_node_sql(
                    node_id=node_id,
                    tenant_id=TENANT_ID,
                    engagement_id=ENGAGEMENT_ID,
                    node_type="stakeholder",
                    title=ev.title or "stakeholder",
                    created_at=occurred_at,
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
        elif ev.kind == "matrix_node_deleted":
            base_lookup = (ev.cluster or "").removesuffix("-out")
            node_id = stakeholder_node_ids.get(base_lookup, det_id(f"stakeholder-node|{base_lookup}"))
            event_id = det_id(f"stakeholder-evt|{ev.cluster}|delete")
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

    decision_node_ids: dict[str, uuid.UUID] = {}
    accept_ledger_ids: dict[str, uuid.UUID] = {}
    for ev in DECISIONS:
        proposal_id = det_id(f"decision-proposal|{ev.cluster}")
        node_id = det_id(f"decision-node|{ev.cluster}")
        created_at = anchor.at(ev.week, ev.day, ev.hour)
        if ev.week <= 4:
            cycle_hours = 24
        elif ev.week <= 12:
            cycle_hours = 72
        elif ev.week <= 16:
            cycle_hours = 168
        elif ev.week <= 19:
            cycle_hours = 96
        else:
            cycle_hours = 72
        decided_at = created_at + timedelta(hours=cycle_hours)

        create_evt_id = det_id(f"decision-create-evt|{ev.cluster}")
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
            statements.append(
                _matrix_node_sql(
                    node_id=node_id,
                    tenant_id=TENANT_ID,
                    engagement_id=ENGAGEMENT_ID,
                    node_type="decision",
                    title=ev.title or ev.summary,
                    created_at=decided_at,
                )
            )
            decision_node_ids[ev.cluster or ""] = node_id
            accept_evt_id = det_id(f"decision-accept-evt|{ev.cluster}")
            accept_ledger_ids[ev.cluster or ""] = accept_evt_id
            causes = [create_evt_id]
            for nev in NARRATIVE:
                if nev.week == ev.week and nev.cluster in cluster_to_event_id:
                    causes.append(cluster_to_event_id[nev.cluster])
                    if len(causes) >= 4:
                        break
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
                    caused_by=causes,
                    affects=[("matrix_node", node_id)],
                )
            )
        elif ev.rejects_acceptance:
            reject_evt_id = det_id(f"decision-reject-evt|{ev.cluster}")
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

    for ev in EXTRACTOR_NOISE:
        proposal_id = det_id(f"extractor-noise-proposal|{ev.cluster}")
        created_at = anchor.at(ev.week, ev.day, ev.hour)
        decided_at = created_at + timedelta(hours=6)
        create_evt_id = det_id(f"extractor-noise-create-evt|{ev.cluster}")
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
        accept_evt_id = det_id(f"extractor-noise-accept-evt|{ev.cluster}")
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
        opened_at = anchor.at(ev.week, ev.day, ev.hour)
        insight_id = det_id(f"risk-insight|{ev.cluster}")
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
        open_evt_id = det_id(f"risk-open-evt|{ev.cluster}")
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

    for ev in RISKS_CLOSED:
        closed_at = anchor.at(ev.week, ev.day, ev.hour)
        insight_id = risk_insight_ids.get(ev.risk_close_of or "", det_id(f"risk-insight|{ev.risk_close_of}"))
        close_evt_id = det_id(f"risk-close-evt|{ev.risk_close_of}")
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

    system_titles = [
        ("Member Portal (web)", 1),
        ("Eligibility Service (mainframe)", 1),
        ("Claims API (Oracle)", 1),
        ("Provider Directory API (HealthwayDirect)", 1),
        ("Member Identity (Okta)", 1),
        ("In-portal Messaging Subsystem", 1),
    ]
    for title, week in system_titles:
        node_id = det_id(f"system-node|{title}")
        created_at = anchor.at(week, 1, 9)
        statements.append(
            _matrix_node_sql(
                node_id=node_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                node_type="system",
                title=title,
                created_at=created_at,
            )
        )
        evt_id = det_id(f"system-evt|{title}")
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

    commitments = [
        ("MSA + BAA signed", 8),
        ("Pilot launch by W24", 20),
        ("Post-pilot expansion decision by W30", 26),
        ("DR drill quarterly post-launch", 26),
    ]
    for title, week in commitments:
        node_id = det_id(f"commit-node|{title}")
        created_at = anchor.at(week, 1, 10)
        statements.append(
            _matrix_node_sql(
                node_id=node_id,
                tenant_id=TENANT_ID,
                engagement_id=ENGAGEMENT_ID,
                node_type="commitment",
                title=title,
                created_at=created_at,
            )
        )
        evt_id = det_id(f"commit-evt|{title}")
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

    def _stk(short_name: str) -> uuid.UUID:
        return det_id(f"stakeholder-node|stakeholder-{short_name}")

    def _dec(cluster: str) -> uuid.UUID:
        return det_id(f"decision-node|{cluster}")

    def _sys(title: str) -> uuid.UUID:
        return det_id(f"system-node|{title}")

    def _commit(title: str) -> uuid.UUID:
        return det_id(f"commit-node|{title}")

    edges_plan: list[tuple[str, uuid.UUID, uuid.UUID, int, str]] = [
        ("sponsors", _stk("vance"), _dec("decision-w1-engagement-model"), 1, "vance-sponsors-engagement-model"),
        ("sponsors", _stk("vance"), _dec("decision-w3-regions"), 3, "vance-sponsors-regions"),
        ("sponsors", _stk("vance"), _dec("decision-w22-phi-scope"), 22, "vance-sponsors-phi-scope"),
        ("sponsors", _stk("vance"), _dec("decision-w26-go"), 26, "vance-sponsors-go"),
        ("sponsors", _stk("kim"), _dec("decision-w20-pilot-slip"), 20, "kim-sponsors-pilot-slip"),
        ("sponsors", _stk("kim"), _dec("decision-w23-comms-cadence"), 23, "kim-sponsors-comms-cadence"),
        ("sponsors", _stk("kim"), _dec("decision-w25-comms"), 25, "kim-sponsors-comms"),
        ("sponsors", _stk("kim"), _dec("decision-w4-messaging"), 14, "kim-sponsors-messaging"),
        ("sponsors", _stk("priya"), _dec("decision-w8-claims"), 14, "priya-sponsors-claims"),
        ("sponsors", _stk("priya"), _dec("decision-w13-observability"), 14, "priya-sponsors-observability"),
        ("sponsors", _stk("priya"), _dec("decision-w15-a11y"), 15, "priya-sponsors-a11y"),
        ("sponsors", _stk("priya"), _dec("decision-w15-cache-warm"), 15, "priya-sponsors-cache-warm"),
        ("sponsors", _stk("patel"), _dec("decision-w2-okta"), 3, "patel-sponsors-okta"),
        ("sponsors", _stk("patel"), _dec("decision-w24-pentest-remediation"), 24, "patel-sponsors-pentest-remediation"),
        ("sponsors", _stk("liu"), _dec("decision-w12-pentest"), 14, "liu-sponsors-pentest"),
        ("owns", _stk("priya"), _sys("Eligibility Service (mainframe)"), 14, "priya-owns-eligibility"),
        ("owns", _stk("priya"), _sys("Claims API (Oracle)"), 14, "priya-owns-claims"),
        ("owns", _stk("priya"), _sys("Member Portal (web)"), 14, "priya-owns-portal"),
        ("owns", _stk("liu"), _sys("Member Identity (Okta)"), 14, "liu-owns-identity"),
        ("owns", _stk("thompson"), _sys("Provider Directory API (HealthwayDirect)"), 22, "thompson-owns-pdapi"),
        ("owns", _stk("kim"), _sys("In-portal Messaging Subsystem"), 14, "kim-owns-messaging-system"),
        ("depends_on", _dec("decision-w2-okta"), _sys("Member Identity (Okta)"), 2, "okta-depends-identity"),
        (
            "depends_on",
            _dec("decision-w4-messaging"),
            _sys("In-portal Messaging Subsystem"),
            4,
            "messaging-depends-msg-sys",
        ),
        ("depends_on", _dec("decision-w5-frontend"), _sys("Member Portal (web)"), 5, "frontend-depends-portal"),
        (
            "depends_on",
            _dec("decision-w6-cache"),
            _sys("Eligibility Service (mainframe)"),
            6,
            "cache-depends-eligibility",
        ),
        ("depends_on", _dec("decision-w8-claims"), _sys("Claims API (Oracle)"), 8, "claims-depends-claims-api"),
        (
            "depends_on",
            _dec("decision-w9-pdapi"),
            _sys("Provider Directory API (HealthwayDirect)"),
            9,
            "pdapi-depends-pdapi",
        ),
        (
            "affects",
            _dec("decision-w13-observability"),
            _sys("Member Portal (web)"),
            13,
            "observability-affects-portal",
        ),
        ("affects", _dec("decision-w15-a11y"), _sys("Member Portal (web)"), 15, "a11y-affects-portal"),
        (
            "affects",
            _dec("decision-w15-cache-warm"),
            _sys("Eligibility Service (mainframe)"),
            15,
            "cache-warm-affects-eligibility",
        ),
        ("affects", _dec("decision-w22-phi-scope"), _sys("Member Identity (Okta)"), 22, "phi-scope-affects-identity"),
        ("owed_to", _commit("MSA + BAA signed"), _stk("patel"), 8, "msa-owed-to-patel"),
        ("owed_to", _commit("Pilot launch by W24"), _stk("vance"), 20, "pilot-owed-to-vance"),
        ("owed_to", _commit("Post-pilot expansion decision by W30"), _stk("kim"), 26, "expansion-owed-to-kim"),
        ("owed_to", _commit("DR drill quarterly post-launch"), _stk("liu"), 26, "dr-owed-to-liu"),
        (
            "blocks",
            _dec("decision-w16-support-ownership"),
            _dec("decision-w20-pilot-slip"),
            20,
            "support-ownership-blocks-pilot-slip",
        ),
        ("enables", _dec("decision-w26-go"), _commit("Pilot launch by W24"), 26, "go-enables-pilot"),
        (
            "depends_on",
            _sys("Member Portal (web)"),
            _sys("Eligibility Service (mainframe)"),
            5,
            "portal-depends-eligibility",
        ),
        ("depends_on", _sys("Member Portal (web)"), _sys("Claims API (Oracle)"), 8, "portal-depends-claims"),
        (
            "depends_on",
            _sys("Member Portal (web)"),
            _sys("Provider Directory API (HealthwayDirect)"),
            9,
            "portal-depends-pdapi",
        ),
        ("depends_on", _sys("Member Portal (web)"), _sys("Member Identity (Okta)"), 2, "portal-depends-identity"),
        ("depends_on", _sys("In-portal Messaging Subsystem"), _sys("Member Portal (web)"), 5, "msg-depends-portal"),
    ]
    for kind, src, dst, week, label in edges_plan:
        edge_id = det_id(f"edge|{label}|{kind}")
        edge_evt_id = det_id(f"edge-evt|{label}|{kind}")
        edge_at = anchor.at(week, 1, 9)
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

    for user_id, role in (
        (USER_STRATEGIST_ID, "deployment_strategist"),
        (USER_FDE_ID, "fde"),
        (USER_BIZDEV_ID, "biz_dev"),
    ):
        evt_id = det_id(f"member-add|{user_id}|{role}")
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

    registry["clusters"] = cluster_to_event_id
    registry["stakeholders"] = stakeholder_node_ids
    registry["decisions"] = decision_node_ids
    registry["accept_ledger"] = accept_ledger_ids
    registry["risks"] = risk_insight_ids

    return "\n".join(statements), registry
