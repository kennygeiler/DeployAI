"""Unit-level smoke for the Phase F1.a ledger ORM module.

No DB — just instantiates the mapped classes to confirm SQLAlchemy can build
them and that the source_kind / entity_kind / severity catalogs stay in sync
with the schema (a sibling slice extends the same constants).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from control_plane.domain.ledger import (
    LEDGER_AFFECTS_ENTITY_KINDS,
    LEDGER_SOURCE_KINDS,
    TEMPORAL_SEVERITIES,
    TEMPORAL_STATUSES,
    LedgerEvent,
    LedgerEventAffects,
    LedgerEventCause,
    TemporalInsight,
)


def test_ledger_event_instantiates_with_defaults() -> None:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    now = datetime.now(UTC)
    row = LedgerEvent(
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=now,
        actor_kind="user",
        actor_id="alice@example.com",
        source_kind="email_ingest",
        source_ref=uuid.uuid4(),
        summary="email arrived",
        detail={"from": "alice@example.com"},
    )
    assert row.tenant_id == tid
    assert row.engagement_id == eid
    assert row.actor_kind == "user"
    assert row.source_kind == "email_ingest"
    assert row.detail == {"from": "alice@example.com"}


def test_ledger_event_cause_pair() -> None:
    parent = uuid.uuid4()
    child = uuid.uuid4()
    edge = LedgerEventCause(event_id=child, caused_by_id=parent)
    assert edge.event_id == child
    assert edge.caused_by_id == parent


def test_ledger_event_affects_polymorphic_kind() -> None:
    eid = uuid.uuid4()
    node = uuid.uuid4()
    edge = LedgerEventAffects(event_id=eid, entity_kind="matrix_node", entity_id=node)
    assert edge.entity_kind == "matrix_node"
    assert edge.entity_id == node


def test_temporal_insight_instantiates() -> None:
    tid = uuid.uuid4()
    start = datetime.now(UTC)
    insight = TemporalInsight(
        tenant_id=tid,
        engagement_id=None,
        insight_kind="stakeholder_churn",
        severity="medium",
        title="Churn spiked",
        narrative="Members removed at 3x prior period.",
        window_start=start,
        window_end=start,
        evidence_event_ids=[uuid.uuid4(), uuid.uuid4()],
        metrics={"prior_rate": 1.0, "current_rate": 3.0},
    )
    assert insight.insight_kind == "stakeholder_churn"
    assert insight.severity == "medium"
    assert len(insight.evidence_event_ids) == 2
    assert insight.metrics["current_rate"] == 3.0


def test_source_kind_catalog_matches_design_doc() -> None:
    expected = {
        "email_ingest",
        "meeting_webhook",
        "manual_capture",
        "llm_proposal_created",
        "proposal_accepted",
        "proposal_rejected",
        "matrix_node_created",
        "matrix_node_updated",
        "matrix_node_deleted",
        "matrix_edge_created",
        "matrix_edge_deleted",
        "insight_opened",
        "insight_closed",
        "recommendation_emitted",
        "recommendation_actioned",
        "engagement_phase_change",
        "member_added",
        "member_removed",
        "settings_change",
        "audit_other",
    }
    assert LEDGER_SOURCE_KINDS == expected


def test_entity_kinds_match_design_doc() -> None:
    assert LEDGER_AFFECTS_ENTITY_KINDS == {
        "matrix_node",
        "matrix_edge",
        "insight",
        "recommendation",
    }


def test_temporal_severity_and_status_enums() -> None:
    assert TEMPORAL_SEVERITIES == ("info", "low", "medium", "high", "critical")
    assert TEMPORAL_STATUSES == ("open", "acknowledged", "dismissed", "resolved", "snoozed")
