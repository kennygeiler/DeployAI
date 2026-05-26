#!/usr/bin/env python3
"""BlueState Health — 26-week end-to-end test bed scenario.

A deterministic, realistic engagement that exercises every Phase F analyzer
with documented ground-truth insights. See
``docs/test-scenarios/bluestate-health.md`` for expected output.

Distinct from ``seed_app.py`` (the smoke fixture); reuses its helpers for
tenant/user setup so a single team owns both engagements.

Usage::

    python3 infra/compose/seed/seed_scenario_bluestate.py
    # or
    make seed-scenario-bluestate

Requires the compose stack up (``make dev``) and the same ``.env`` as
``seed_app.py``. Idempotent: re-running upserts the same UUIDs.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from scenario_data.bluestate_events import (  # noqa: E402
    ALL_EVENTS,
    DECISIONS,
    EXTRACTOR_NOISE,
    NARRATIVE,
    RISKS_CLOSED,
    RISKS_OPENED,
    STAKEHOLDERS,
)
from seed_app import (  # noqa: E402
    COMPOSE_FILE,
    ENV,
    ENV_FILE,
    POSTGRES_DB,
    POSTGRES_USER,
    TENANT_ID,
    USER_BIZDEV_ID,
    USER_FDE_ID,
    USER_STRATEGIST_ID,
    _psql,
    _wait_for_cp,
    seed_engagement,
    seed_members,
    seed_tenant_and_users,
)

_POSTGRES_PASSWORD = ENV.get("POSTGRES_PASSWORD", "deployai-local-dev")
# Inside the compose network the CP container reaches Postgres on hostname
# `postgres` — same as the production compose URL. Loaded from .env so an
# owner who rotated the local-dev password doesn't have to edit this file.
_INTERNAL_DB_URL = (
    f"postgresql+psycopg://{POSTGRES_USER}:{_POSTGRES_PASSWORD}@postgres:5432/{POSTGRES_DB}"
)

# Engagement constants
ENGAGEMENT_ID = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
ENGAGEMENT_NAME = "BlueState Health — Member Portal Replatform"
CUSTOMER_ACCOUNT = "BlueState Health"
ENGAGEMENT_PHASE = "build"

# W26 ends 21 days before "now" so the trailing 14d wall-clock window is
# reliably event-free (engagement_silence default window is 14d; 21d here
# leaves slack so a slightly stale seed run still keeps it empty). All other
# analyzers are run at synthetic ``now`` time points within the scenario via
# direct programmatic calls.
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
    """SQL-escape a string literal."""
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
    """Build the SQL block to insert one ledger row and its edges."""
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
    """Insert one matrix_nodes row, idempotent on id."""
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
    """Soft-delete: actually delete row (matrix_node_deleted ledger event is the marker)."""
    return f"DELETE FROM matrix_nodes WHERE id = '{node_id}'::uuid;\n"


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
    """Insert one matrix_insights (Oracle) row — these underpin insight_opened/closed ledger events."""
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


def build_scenario_sql(anchor: TimeAnchor) -> tuple[str, dict[str, dict[str, uuid.UUID]]]:
    """Construct the full multi-statement SQL block for the scenario.

    Returns ``(sql, registry)`` where ``registry`` maps cluster IDs to the
    UUIDs they produced (used for ground-truth doc + verification).
    """
    statements: list[str] = ["BEGIN;"]
    registry: dict[str, dict[str, uuid.UUID]] = {}

    # Deterministic UUID namespace for this scenario so re-runs are stable.
    ns = uuid.UUID("88888888-1234-5678-9abc-bbbbbbbbbbbb")

    def det_id(label: str) -> uuid.UUID:
        return uuid.uuid5(ns, label)

    # ---- 1. Narrative events: emit one ledger row per event.
    cluster_to_event_id: dict[str, uuid.UUID] = {}
    for ev in NARRATIVE:
        event_id = det_id(f"narrative|{ev.cluster}")
        cluster_to_event_id[ev.cluster] = event_id
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

    # ---- 2. Stakeholder churn: matrix_node create/delete events.
    stakeholder_node_ids: dict[str, uuid.UUID] = {}
    for ev in STAKEHOLDERS:
        occurred_at = anchor.at(ev.week, ev.day, ev.hour)
        if ev.kind == "matrix_node_created":
            node_id = det_id(f"stakeholder-node|{ev.cluster}")
            stakeholder_node_ids[ev.cluster] = node_id
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
            # Cluster is foo-out; strip the suffix to find the original add.
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

    # ---- 3. Decisions: llm_proposal_created → proposal_accepted/rejected pairs.
    # Cycle creation→accept time encodes the period (fast in design, slow in pilot prep).
    decision_node_ids: dict[str, uuid.UUID] = {}
    accept_ledger_ids: dict[str, uuid.UUID] = {}
    for ev in DECISIONS:
        proposal_id = det_id(f"decision-proposal|{ev.cluster}")
        node_id = det_id(f"decision-node|{ev.cluster}")
        created_at = anchor.at(ev.week, ev.day, ev.hour)
        # Cycle calibration. Build phase ~7d (vs design ~3d) pushes decision_cycle_slowdown
        # over the 50% growth threshold at W16 end. W20+ kept at ~3d so the W22-24
        # create+accept pairs all land inside a 14d window for extractor_acceptance_drift.
        if ev.week <= 4:
            cycle_hours = 24  # ~1 day in discovery
        elif ev.week <= 12:
            cycle_hours = 72  # ~3 days in design
        elif ev.week <= 16:
            cycle_hours = 168  # ~7 days build (cycle creeping)
        elif ev.week <= 19:
            cycle_hours = 96
        else:
            cycle_hours = 72  # 3d so all W22-24 pairs sit inside a 14d drift window
        decided_at = created_at + timedelta(hours=cycle_hours)

        # llm_proposal_created ledger event
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
            # Create the matrix_node (decision) on accept
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
            decision_node_ids[ev.cluster] = node_id
            accept_evt_id = det_id(f"decision-accept-evt|{ev.cluster}")
            accept_ledger_ids[ev.cluster] = accept_evt_id
            # Build causal chain: link accept → create-evt, and → any narrative
            # events in the same week (richer chain for provenance_summary).
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

    # ---- 3b. Extractor noise — quick llm_proposal_created + proposal_accepted pairs
    # without creating actual matrix nodes. These pad the trailing 30d acceptance
    # baseline so extractor_acceptance_drift can fire @ end W24 (where the W23-24
    # reject cluster is the trailing-14d signal).
    for ev in EXTRACTOR_NOISE:
        proposal_id = det_id(f"extractor-noise-proposal|{ev.cluster}")
        created_at = anchor.at(ev.week, ev.day, ev.hour)
        decided_at = created_at + timedelta(hours=6)  # tight cycle so accept lands in same 14d window
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

    # ---- 4. Risks: matrix_insights (oracle) + insight_opened/closed ledger events.
    risk_insight_ids: dict[str, uuid.UUID] = {}
    for ev in RISKS_OPENED:
        opened_at = anchor.at(ev.week, ev.day, ev.hour)
        insight_id = det_id(f"risk-insight|{ev.cluster}")
        risk_insight_ids[ev.cluster] = insight_id
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

    # ---- 5. System nodes (a few, for matrix totals)
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

    # ---- 6. Commitments (a few)
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

    # ---- 7. Member add/remove ledger events for the three team members (already in DB via API)
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


def backfill_snapshots(engagement_id: str) -> None:
    """Backfill 182 daily matrix snapshots for the engagement (via CP container).

    The standalone ``control_plane.cli.snapshot_backfill`` entry point does not
    import every model module up-front and that races with SQLAlchemy's lazy FK
    resolution against ``app_tenants``. We call ``backfill_snapshots`` directly
    after explicitly importing the missing model so the FK metadata resolves.
    """
    print(f"seed: backfilling 182 snapshots for {engagement_id}…")
    import subprocess

    snippet = (
        "import asyncio, uuid\n"
        "from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine\n"
        # Import every model module the FKs reference so they're in the metadata
        # registry before SQLAlchemy emits its first query.
        "import control_plane.domain.app_identity.models  # noqa: F401\n"
        "import control_plane.domain.engagement  # noqa: F401\n"
        "import control_plane.domain.matrix_snapshot  # noqa: F401\n"
        "from control_plane.snapshots.cron import backfill_snapshots\n"
        f"URL = {_INTERNAL_DB_URL!r}\n"
        f"TENANT_ID = uuid.UUID('{TENANT_ID}')\n"
        f"ENGAGEMENT_ID = uuid.UUID('{engagement_id}')\n"
        "async def main():\n"
        "    engine = create_async_engine(URL)\n"
        "    Session = async_sessionmaker(engine, expire_on_commit=False)\n"
        "    async with Session() as s:\n"
        "        n = await backfill_snapshots(s, tenant_id=TENANT_ID, engagement_id=ENGAGEMENT_ID, days=182, rebuild=True)\n"
        "        await s.commit()\n"
        "        print('wrote', n, 'snapshots')\n"
        "    await engine.dispose()\n"
        "asyncio.run(main())\n"
    )
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "control-plane",
        "python",
        "-c",
        snippet,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit(f"snapshot backfill failed (rc={r.returncode})")


def run_analyzers_at(now_iso: str) -> None:
    """Invoke run_analyzers programmatically inside the CP container with a custom now.

    The HTTP /intelligence/run endpoint always uses datetime.now(UTC); to make all
    six analyzers fire against a multi-week scenario we shell into the CP container
    and call run_analyzers directly with a synthetic ``now`` time anchored in the
    scenario.
    """
    import subprocess

    snippet = (
        "import asyncio, uuid\n"
        "from datetime import datetime\n"
        "from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine\n"
        "from control_plane.intelligence.scheduler import run_analyzers\n"
        f"URL = {_INTERNAL_DB_URL!r}\n"
        f"TENANT_ID = uuid.UUID('{TENANT_ID}')\n"
        f"ENGAGEMENT_ID = uuid.UUID('{ENGAGEMENT_ID}')\n"
        f"NOW = datetime.fromisoformat('{now_iso}')\n"
        "async def main():\n"
        "    engine = create_async_engine(URL)\n"
        "    Session = async_sessionmaker(engine, expire_on_commit=False)\n"
        "    async with Session() as s:\n"
        "        w = await run_analyzers(s, tenant_id=TENANT_ID, engagement_id=ENGAGEMENT_ID, now=NOW)\n"
        "        await s.commit()\n"
        "        print('wrote', len(w), 'insights for now=' + NOW.isoformat())\n"
        "    await engine.dispose()\n"
        "asyncio.run(main())\n"
    )
    cmd = [
        "docker",
        "compose",
        "--env-file",
        str(ENV_FILE),
        "-f",
        str(COMPOSE_FILE),
        "exec",
        "-T",
        "control-plane",
        "python",
        "-c",
        snippet,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    sys.stdout.write(r.stdout)
    if r.returncode != 0:
        sys.stderr.write(r.stderr)
        raise SystemExit(f"run_analyzers (now={now_iso}) failed (rc={r.returncode})")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-snapshots",
        action="store_true",
        help="Skip snapshot backfill (faster reruns for content iteration).",
    )
    parser.add_argument(
        "--skip-analyzers",
        action="store_true",
        help="Skip running analyzers (manual run later via the helper).",
    )
    args = parser.parse_args()

    print(f"seed: target tenant={TENANT_ID}")
    print(f"seed: engagement_id={ENGAGEMENT_ID}")
    print(f"seed: events to emit = {len(ALL_EVENTS)}")

    _wait_for_cp()
    seed_tenant_and_users()
    seed_engagement(ENGAGEMENT_ID, ENGAGEMENT_NAME, CUSTOMER_ACCOUNT)
    seed_members(
        ENGAGEMENT_ID,
        [
            (USER_STRATEGIST_ID, "deployment_strategist"),
            (USER_FDE_ID, "fde"),
            (USER_BIZDEV_ID, "biz_dev"),
        ],
    )

    base_now = datetime.now(UTC)
    anchor = TimeAnchor(base_now=base_now)
    print(f"seed: W1 Monday   = {anchor.w1_monday.isoformat()}")
    print(f"seed: W26 end     = {anchor.w26_end.isoformat()}")
    print(
        f"seed: NOW         = {base_now.isoformat()} (trailing {TRAILING_SILENCE_DAYS}d silent for engagement_silence)"
    )

    sql, registry = build_scenario_sql(anchor)
    print(f"seed: applying ledger + matrix scenario SQL ({len(sql)} chars)…")
    _psql(sql)

    if not args.skip_snapshots:
        backfill_snapshots(ENGAGEMENT_ID)

    if not args.skip_analyzers:
        # Pin analyzer runs to scenario time anchors so each analyzer's default
        # window (14d to 30d) hits the right event cluster. The /intelligence/run
        # HTTP endpoint always uses datetime.now(UTC), which from a single
        # invocation can only fire one or two of the six analyzers on a 26-week
        # corpus. The cleanest workaround is to call run_analyzers programmatically
        # at several `now` values that each materialize one of the expected insights.
        # See docs/test-scenarios/bluestate-health.md § "Analyzer run schedule".
        w14_end = anchor.at(14, 7, 23)  # stakeholder_churn (deletes in current 30d, prior empty)
        w16_end_plus1 = anchor.at(16, 7, 23) + timedelta(days=1)  # decision_cycle_slowdown
        w22_end_plus1 = anchor.at(22, 7, 23) + timedelta(days=1)  # risk_open_rate
        w24_end_plus2 = anchor.at(24, 7, 23) + timedelta(days=2)  # extractor_acceptance_drift
        go_create = anchor.at(26, 2, 15)
        go_accept_plus12 = go_create + timedelta(hours=72 + 12)  # decision_provenance_summary
        runs = (
            ("W14 end → stakeholder_churn", w14_end),
            ("W16 end+1d → decision_cycle_slowdown", w16_end_plus1),
            ("W22 end+1d → risk_open_rate", w22_end_plus1),
            ("W24 end+2d → extractor_acceptance_drift", w24_end_plus2),
            ("W26 GO accept +12h → decision_provenance_summary", go_accept_plus12),
            ("now → engagement_silence", base_now),
        )
        for label, t in runs:
            print(f"seed: running analyzers @ {label} ({t.isoformat()})…")
            run_analyzers_at(t.isoformat())

    # Final tallies
    print()
    print("seed: scenario complete.")
    print(f"  Engagement:  {ENGAGEMENT_ID}")
    print(f"  Tenant:      {TENANT_ID}")
    print(f"  Stakeholder nodes seeded: {len(registry['stakeholders'])}")
    print(f"  Decision nodes seeded:    {len(registry['decisions'])}")
    print(f"  Risks seeded:             {len(registry['risks'])}")
    print()
    print("Verify counts via:")
    print(
        "  docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai "
        "-c \"SELECT source_kind, count(*) FROM ledger_events WHERE engagement_id='"
        + ENGAGEMENT_ID
        + "' GROUP BY 1 ORDER BY 2 DESC;\""
    )
    print(
        "  docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai "
        "-c \"SELECT count(*) FROM matrix_snapshots WHERE engagement_id='" + ENGAGEMENT_ID + "';\""
    )
    print(
        "  docker compose -f infra/compose/docker-compose.yml exec postgres psql -U deployai -d deployai "
        "-c \"SELECT insight_kind, severity, title FROM temporal_insights WHERE engagement_id='"
        + ENGAGEMENT_ID
        + "' ORDER BY created_at;\""
    )


if __name__ == "__main__":
    main()
