"""Procedural event templates for one portfolio engagement.

Generates a ledger / matrix / insight payload for one ``EngagementConfig``
parameterised so semantic content (customer name, stakeholders, system
titles, decisions, risks) differs per engagement. UUIDs are deterministic
via uuid5 seeded by the engagement's namespace so re-seed is idempotent.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from control_plane.scenarios.portfolio.engagements import EngagementConfig

TRAILING_SILENCE_DAYS = 21


@dataclass
class TimeAnchor:
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
    namespace: str,
) -> str:
    decided_sql = f"'{decided_at.isoformat()}'::timestamptz" if decided_at else "NULL"
    decided_by_sql = "'auto'" if decided_at else "NULL"
    dedup = f"portfolio-{namespace}-{insight_id.hex[:16]}"
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


_NARRATIVE_KINDS = (
    ("email", "user", "weekly status update from {customer}"),
    ("meeting_note", "user", "steering committee notes — {customer}"),
    ("slack", "user", "ops channel sync — {customer}"),
    ("doc", "user", "design memo update — {customer}"),
    ("email", "user", "vendor follow-up — {customer}"),
    ("meeting_note", "user", "review of {customer} milestones"),
    ("slack", "user", "blocker triage — {customer}"),
    ("doc", "user", "risk review entry — {customer}"),
    ("email", "user", "executive briefing — {customer}"),
    ("meeting_note", "user", "{customer} architecture review"),
)


def build_engagement_sql(
    config: EngagementConfig,
    *,
    tenant_id: str,
    anchor: TimeAnchor,
    actor_email: str = "sarah.chen@deployai.com",
) -> str:
    """Procedurally generate the SQL payload for one engagement.

    Returns one INSERT block (no BEGIN/COMMIT — the runner manages txn).
    Distinct customer / stakeholder / system content per engagement keeps
    cross-engagement isolation tests meaningful.
    """
    ns = uuid.uuid5(uuid.NAMESPACE_DNS, f"portfolio:{config.namespace}")

    def det_id(label: str) -> uuid.UUID:
        return uuid.uuid5(ns, label)

    statements: list[str] = []

    narrative_event_ids: list[uuid.UUID] = []
    for week in range(1, 27):
        for slot in range(10):
            kind_idx = (week + slot) % len(_NARRATIVE_KINDS)
            kind, actor_kind, summary_tmpl = _NARRATIVE_KINDS[kind_idx]
            event_id = det_id(f"narrative|w{week}|s{slot}")
            narrative_event_ids.append(event_id)
            occurred_at = anchor.at(week, ((slot % 5) + 1), 9 + (slot % 8))
            summary = summary_tmpl.format(customer=config.customer_account)
            topic = config.decision_titles[(week - 1) % len(config.decision_titles)][1]
            body_excerpt = (
                f"{config.customer_account} ({config.industry}) - week {week} update covering "
                f"{config.namespace} delivery progress. Topics: {topic}."
            )
            statements.append(
                _emit_ledger_sql(
                    event_id=event_id,
                    tenant_id=tenant_id,
                    engagement_id=config.engagement_id,
                    occurred_at=occurred_at,
                    actor_kind=actor_kind,
                    actor_id=actor_email,
                    source_kind=kind,
                    source_ref=None,
                    summary=summary,
                    detail_json='{"body_excerpt": "' + _q(body_excerpt[:200]) + '"}',
                )
            )

    stakeholder_node_ids: dict[str, uuid.UUID] = {}
    for idx, stk in enumerate(config.stakeholders):
        node_id = det_id(f"stakeholder-node|{stk.short}")
        stakeholder_node_ids[stk.short] = node_id
        week = 1 if idx < 3 else min(2 + (idx - 3), 10)
        created_at = anchor.at(week, 1, 10 + (idx % 6))
        evt_id = det_id(f"stakeholder-evt|{stk.short}|create")
        evidence = [evt_id]
        for nev_id in narrative_event_ids[(idx * 5) : (idx * 5) + 4]:
            if nev_id not in evidence:
                evidence.append(nev_id)
        title = f"{stk.full_name} ({stk.role})"
        statements.append(
            _matrix_node_sql(
                node_id=node_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                node_type="stakeholder",
                title=title,
                created_at=created_at,
                evidence_event_ids=evidence,
            )
        )
        statements.append(
            _emit_ledger_sql(
                event_id=evt_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                occurred_at=created_at,
                actor_kind="user",
                actor_id=actor_email,
                source_kind="matrix_node_created",
                source_ref=node_id,
                summary=f"stakeholder added: {stk.full_name}, {stk.role}",
                detail_json='{"node_type": "stakeholder", "title": "' + _q(title) + '"}',
                affects=[("matrix_node", node_id)],
            )
        )

    for idx, short in enumerate(config.departed_short_names):
        if short not in stakeholder_node_ids:
            continue
        depart_week = 14 + idx
        depart_at = anchor.at(depart_week, 2, 9 + idx)
        node_id = stakeholder_node_ids[short]
        evt_id = det_id(f"stakeholder-evt|{short}|depart")
        statements.append(_delete_matrix_node_sql(node_id))
        statements.append(
            _emit_ledger_sql(
                event_id=evt_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                occurred_at=depart_at,
                actor_kind="user",
                actor_id=actor_email,
                source_kind="matrix_node_deleted",
                source_ref=node_id,
                summary=f"stakeholder departed: {short}",
                detail_json='{"node_type": "stakeholder"}',
            )
        )

    system_node_ids: dict[str, uuid.UUID] = {}
    for sys_def in config.systems:
        node_id = det_id(f"system-node|{sys_def.title}")
        system_node_ids[sys_def.title] = node_id
        created_at = anchor.at(sys_def.intro_week, 1, 9)
        evt_id = det_id(f"system-evt|{sys_def.title}")
        statements.append(
            _matrix_node_sql(
                node_id=node_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                node_type="system",
                title=sys_def.title,
                created_at=created_at,
                evidence_event_ids=[evt_id, *narrative_event_ids[:4]],
            )
        )
        statements.append(
            _emit_ledger_sql(
                event_id=evt_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                occurred_at=created_at,
                actor_kind="user",
                actor_id=actor_email,
                source_kind="matrix_node_created",
                source_ref=node_id,
                summary=f"system node added: {sys_def.title}",
                detail_json='{"node_type": "system", "title": "' + _q(sys_def.title) + '"}',
                affects=[("matrix_node", node_id)],
            )
        )

    decision_node_ids: dict[int, uuid.UUID] = {}
    for week, dec_title in config.decision_titles:
        proposal_id = det_id(f"decision-proposal|w{week}|{dec_title[:40]}")
        node_id = det_id(f"decision-node|w{week}|{dec_title[:40]}")
        decision_node_ids[week] = node_id
        created_at = anchor.at(week, 2, 10)
        decided_at = created_at + timedelta(hours=48)
        create_evt_id = det_id(f"decision-create|w{week}|{dec_title[:40]}")
        accept_evt_id = det_id(f"decision-accept|w{week}|{dec_title[:40]}")
        statements.append(
            _emit_ledger_sql(
                event_id=create_evt_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                occurred_at=created_at,
                actor_kind="agent:matrix_extractor",
                actor_id="cartographer",
                source_kind="llm_proposal_created",
                source_ref=proposal_id,
                summary=f"proposal drafted: decision — {dec_title}"[:500],
                detail_json='{"proposal_kind": "node", "node_type": "decision", "title": "' + _q(dec_title) + '"}',
            )
        )
        narrative_slice = narrative_event_ids[(week - 1) % 30 : (week - 1) % 30 + 3]
        statements.append(
            _matrix_node_sql(
                node_id=node_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                node_type="decision",
                title=dec_title,
                created_at=decided_at,
                evidence_event_ids=[create_evt_id, accept_evt_id, *narrative_slice],
            )
        )
        statements.append(
            _emit_ledger_sql(
                event_id=accept_evt_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                occurred_at=decided_at,
                actor_kind="user",
                actor_id=actor_email,
                source_kind="proposal_accepted",
                source_ref=proposal_id,
                summary=f"proposal accepted: decision — {dec_title}"[:500],
                detail_json='{"proposal_kind": "node", "node_type": "decision", "result_node_id": "'
                + str(node_id)
                + '"}',
                caused_by=[create_evt_id],
                affects=[("matrix_node", node_id)],
            )
        )

    risk_insight_ids: dict[int, uuid.UUID] = {}
    for week, risk_title in config.risk_titles:
        insight_id = det_id(f"risk-insight|w{week}|{risk_title[:40]}")
        risk_insight_ids[week] = insight_id
        opened_at = anchor.at(week, 3, 11)
        body = (
            f"{config.customer_account} — risk surfaced in week {week}. Topic: {risk_title}. "
            f"Owner area: {config.industry}."
        )
        statements.append(
            _matrix_insight_sql(
                insight_id=insight_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                title=risk_title,
                body=body,
                severity="medium",
                created_at=opened_at,
                namespace=config.namespace,
            )
        )
        open_evt_id = det_id(f"risk-open|w{week}|{risk_title[:40]}")
        statements.append(
            _emit_ledger_sql(
                event_id=open_evt_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                occurred_at=opened_at,
                actor_kind="agent:oracle",
                actor_id="oracle",
                source_kind="insight_opened",
                source_ref=insight_id,
                summary=f"risk opened: {risk_title}"[:500],
                detail_json='{"node_type": "risk", "insight_type": "risk", "severity": "medium", "agent": "oracle"}',
                affects=[("insight", insight_id)],
            )
        )

        if week % 3 == 0:
            close_week = min(week + 4, 26)
            closed_at = anchor.at(close_week, 4, 14)
            close_evt_id = det_id(f"risk-close|w{week}|{risk_title[:40]}")
            statements.append(
                f"UPDATE matrix_insights SET status = 'resolved', "
                f"decided_at = '{closed_at.isoformat()}'::timestamptz, decided_by = 'auto' "
                f"WHERE id = '{insight_id}'::uuid;\n"
            )
            statements.append(
                _emit_ledger_sql(
                    event_id=close_evt_id,
                    tenant_id=tenant_id,
                    engagement_id=config.engagement_id,
                    occurred_at=closed_at,
                    actor_kind="system",
                    actor_id="auto",
                    source_kind="insight_closed",
                    source_ref=insight_id,
                    summary=f"risk closed: {risk_title}"[:500],
                    detail_json=(
                        '{"node_type": "risk", "insight_type": "risk", "severity": "medium",'
                        ' "agent": "oracle", "status": "resolved"}'
                    ),
                    affects=[("insight", insight_id)],
                )
            )

    commitment_node_ids: dict[str, uuid.UUID] = {}
    for week, commit_title in config.commitments:
        node_id = det_id(f"commit-node|{commit_title}")
        commitment_node_ids[commit_title] = node_id
        created_at = anchor.at(week, 1, 10)
        evt_id = det_id(f"commit-evt|{commit_title}")
        statements.append(
            _matrix_node_sql(
                node_id=node_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                node_type="commitment",
                title=commit_title,
                created_at=created_at,
                evidence_event_ids=[evt_id, *narrative_event_ids[(week - 1) % 25 : (week - 1) % 25 + 3]],
            )
        )
        statements.append(
            _emit_ledger_sql(
                event_id=evt_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                occurred_at=created_at,
                actor_kind="user",
                actor_id=actor_email,
                source_kind="matrix_node_created",
                source_ref=node_id,
                summary=f"commitment node added: {commit_title}"[:500],
                detail_json='{"node_type": "commitment", "title": "' + _q(commit_title) + '"}',
                affects=[("matrix_node", node_id)],
            )
        )

    edges_plan: list[tuple[str, uuid.UUID, uuid.UUID, int, str]] = []

    departed = set(config.departed_short_names)
    sponsor_pool = [node_id for short, node_id in stakeholder_node_ids.items() if short not in departed]
    decision_weeks_sorted = sorted(decision_node_ids.keys())
    for idx, week in enumerate(decision_weeks_sorted):
        decision_id = decision_node_ids[week]
        sponsor_id = sponsor_pool[idx % len(sponsor_pool)]
        edges_plan.append(("sponsors", sponsor_id, decision_id, week, f"sponsor-d{week}-{idx}"))

    system_list = list(system_node_ids.values())
    for idx, week in enumerate(decision_weeks_sorted):
        if idx % 2 != 0:
            continue
        decision_id = decision_node_ids[week]
        target_system = system_list[idx % len(system_list)]
        edges_plan.append(("depends_on", decision_id, target_system, week, f"dep-d{week}-s{idx}"))

    for idx, (sys_title, node_id) in enumerate(system_node_ids.items()):
        owner = sponsor_pool[(idx + 1) % len(sponsor_pool)]
        edges_plan.append(("owns", owner, node_id, 4, f"owns-{sys_title[:24]}"))

    for idx in range(len(system_list) - 1):
        edges_plan.append(("depends_on", system_list[idx], system_list[idx + 1], 6, f"sys-chain-{idx}"))

    for idx, (commit_title, commit_id) in enumerate(commitment_node_ids.items()):
        owed_to = sponsor_pool[idx % len(sponsor_pool)]
        edges_plan.append(("owed_to", commit_id, owed_to, 16, f"commit-owed-{commit_title[:24]}"))

    for kind, src, dst, week, label in edges_plan:
        edge_id = det_id(f"edge|{label}|{kind}")
        edge_evt_id = det_id(f"edge-evt|{label}|{kind}")
        edge_at = anchor.at(week, 1, 9)
        statements.append(
            _matrix_edge_sql(
                edge_id=edge_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                edge_type=kind,
                from_node_id=src,
                to_node_id=dst,
                created_at=edge_at,
            )
        )
        statements.append(
            _emit_ledger_sql(
                event_id=edge_evt_id,
                tenant_id=tenant_id,
                engagement_id=config.engagement_id,
                occurred_at=edge_at,
                actor_kind="user",
                actor_id=actor_email,
                source_kind="matrix_edge_created",
                source_ref=edge_id,
                summary=f"edge: {kind} ({label})"[:500],
                detail_json='{"edge_type": "' + kind + '"}',
                affects=[("matrix_edge", edge_id)],
            )
        )

    return "\n".join(statements)
