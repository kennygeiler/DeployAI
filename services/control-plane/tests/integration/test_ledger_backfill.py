"""Integration: ledger_backfill CLI seeds rows from source tables idempotently."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text

from control_plane.cli import ledger_backfill

pytestmark = pytest.mark.integration


def _sync_url(eng: Engine) -> str:
    return eng.url.render_as_string(hide_password=False)


def _seed_source_rows(eng: Engine) -> tuple[uuid.UUID, uuid.UUID, dict[str, int]]:
    """Seed one tenant + engagement + a row in each of the source tables.

    Returns ``(tenant_id, engagement_id, expected_per_source_kind)``.
    """
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    now = datetime.now(UTC)

    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'backfill-test')"),
            {"t": str(tenant_id)},
        )
        engagement_id = conn.execute(
            text("INSERT INTO engagements (tenant_id, name) VALUES (:t, 'Backfill Test') RETURNING id"),
            {"t": str(tenant_id)},
        ).scalar_one()

        # email_ingest_events
        conn.execute(
            text(
                "INSERT INTO email_ingest_events "
                "(tenant_id, engagement_id, source, raw_payload, parsed_subject) "
                "VALUES (:t, :e, 'paste', 'hello world', 'Subject A')"
            ),
            {"t": str(tenant_id), "e": str(engagement_id)},
        )

        # meeting_webhook_events
        conn.execute(
            text(
                "INSERT INTO meeting_webhook_events "
                "(tenant_id, engagement_id, source, external_event_id) "
                "VALUES (:t, :e, 'zoom', 'evt-001')"
            ),
            {"t": str(tenant_id), "e": str(engagement_id)},
        )

        # canonical_memory_event — required for matrix_proposals FK
        cm_event_id = conn.execute(
            text(
                "INSERT INTO canonical_memory_events "
                "(tenant_id, engagement_id, event_type, occurred_at) "
                "VALUES (:t, :e, 'meeting.held', now()) RETURNING id"
            ),
            {"t": str(tenant_id), "e": str(engagement_id)},
        ).scalar_one()

        # matrix_node first (accepted proposal will reference it)
        node_id = conn.execute(
            text(
                "INSERT INTO matrix_nodes (tenant_id, engagement_id, node_type, title) "
                "VALUES (:t, :e, 'system', 'LiDAR ingest') RETURNING id"
            ),
            {"t": str(tenant_id), "e": str(engagement_id)},
        ).scalar_one()

        # second node so we can wire an edge
        node_two = conn.execute(
            text(
                "INSERT INTO matrix_nodes (tenant_id, engagement_id, node_type, title) "
                "VALUES (:t, :e, 'risk', 'Calibration slip') RETURNING id"
            ),
            {"t": str(tenant_id), "e": str(engagement_id)},
        ).scalar_one()

        # matrix_edge
        conn.execute(
            text(
                "INSERT INTO matrix_edges "
                "(tenant_id, engagement_id, edge_type, from_node_id, to_node_id) "
                "VALUES (:t, :e, 'threatens', :a, :b)"
            ),
            {"t": str(tenant_id), "e": str(engagement_id), "a": str(node_two), "b": str(node_id)},
        )

        # accepted matrix_proposal
        conn.execute(
            text(
                "INSERT INTO matrix_proposals "
                "(tenant_id, engagement_id, source_event_id, proposal_kind, "
                " status, decided_at, decided_by, result_node_id) "
                "VALUES (:t, :e, :se, 'node', 'accepted', :da, :du, :rn)"
            ),
            {
                "t": str(tenant_id),
                "e": str(engagement_id),
                "se": str(cm_event_id),
                "da": now,
                "du": str(user_id),
                "rn": str(node_id),
            },
        )

        # rejected matrix_proposal
        conn.execute(
            text(
                "INSERT INTO matrix_proposals "
                "(tenant_id, engagement_id, source_event_id, proposal_kind, "
                " status, decided_at, decided_by) "
                "VALUES (:t, :e, :se, 'edge', 'rejected', :da, :du)"
            ),
            {
                "t": str(tenant_id),
                "e": str(engagement_id),
                "se": str(cm_event_id),
                "da": now,
                "du": str(user_id),
            },
        )

        # matrix_insight (open)
        conn.execute(
            text(
                "INSERT INTO matrix_insights "
                "(tenant_id, engagement_id, agent, insight_type, severity, title, body, dedup_key) "
                "VALUES (:t, :e, 'oracle', 'risk_emergent', 'medium', 'Cal slip risk', "
                "        'body', 'dk-001')"
            ),
            {"t": str(tenant_id), "e": str(engagement_id)},
        )

        # matrix_insight (resolved) so insight_closed lands too
        conn.execute(
            text(
                "INSERT INTO matrix_insights "
                "(tenant_id, engagement_id, agent, insight_type, severity, title, body, "
                " dedup_key, status, decided_at) "
                "VALUES (:t, :e, 'oracle', 'risk_emergent', 'low', 'old risk', 'body', "
                "        'dk-002', 'resolved', :da)"
            ),
            {"t": str(tenant_id), "e": str(engagement_id), "da": now - timedelta(days=1)},
        )

    expected = {
        "email_ingest": 1,
        "meeting_webhook": 1,
        "llm_proposal_created": 2,
        "proposal_accepted": 1,
        "proposal_rejected": 1,
        "matrix_node_created": 2,
        "matrix_edge_created": 1,
        "insight_opened": 2,
        "insight_closed": 1,
    }
    return tenant_id, engagement_id, expected


def test_backfill_dry_run_reports_plan_without_writing(postgres_engine: Engine) -> None:
    tenant_id, _, expected = _seed_source_rows(postgres_engine)

    result = ledger_backfill.run(_sync_url(postgres_engine), tenant_id, dry_run=True)
    assert result["dry_run"] is True
    assert result["planned_counts"] == expected
    assert result["total_planned"] == sum(expected.values())

    with postgres_engine.connect() as conn:
        count = conn.execute(
            text("SELECT count(*) FROM ledger_events WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        ).scalar_one()
    assert count == 0


def test_backfill_writes_one_event_per_source_row(postgres_engine: Engine) -> None:
    tenant_id, _, expected = _seed_source_rows(postgres_engine)

    result = ledger_backfill.run(_sync_url(postgres_engine), tenant_id, dry_run=False)
    assert result["written_counts"] == expected

    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT source_kind, count(*) AS n FROM ledger_events WHERE tenant_id = :t GROUP BY source_kind"),
            {"t": str(tenant_id)},
        ).all()
    actual = {r.source_kind: r.n for r in rows}
    assert actual == expected


def test_backfill_is_idempotent(postgres_engine: Engine) -> None:
    tenant_id, _, expected = _seed_source_rows(postgres_engine)

    first = ledger_backfill.run(_sync_url(postgres_engine), tenant_id, dry_run=False)
    assert first["total_written"] == sum(expected.values())

    second = ledger_backfill.run(_sync_url(postgres_engine), tenant_id, dry_run=False)
    assert second["written_counts"] == {}
    assert second["total_written"] == 0

    with postgres_engine.connect() as conn:
        total = conn.execute(
            text("SELECT count(*) FROM ledger_events WHERE tenant_id = :t"),
            {"t": str(tenant_id)},
        ).scalar_one()
    assert total == sum(expected.values())


def test_backfill_links_cause_and_affect_edges(postgres_engine: Engine) -> None:
    tenant_id, _, _ = _seed_source_rows(postgres_engine)
    ledger_backfill.run(_sync_url(postgres_engine), tenant_id, dry_run=False)

    with postgres_engine.connect() as conn:
        cause_count = conn.execute(
            text(
                "SELECT count(*) FROM ledger_event_causes c "
                "JOIN ledger_events e ON e.id = c.event_id "
                "WHERE e.tenant_id = :t AND e.source_kind IN "
                "('proposal_accepted','proposal_rejected','insight_closed')"
            ),
            {"t": str(tenant_id)},
        ).scalar_one()
        assert cause_count >= 1

        affect_rows = conn.execute(
            text(
                "SELECT a.entity_kind, count(*) AS n "
                "FROM ledger_event_affects a "
                "JOIN ledger_events e ON e.id = a.event_id "
                "WHERE e.tenant_id = :t "
                "GROUP BY a.entity_kind"
            ),
            {"t": str(tenant_id)},
        ).all()
    by_kind = {r.entity_kind: r.n for r in affect_rows}
    assert by_kind.get("matrix_node", 0) >= 2
    assert by_kind.get("matrix_edge", 0) >= 1
    assert by_kind.get("insight", 0) >= 2


def test_cli_main_dry_run_emits_json(postgres_engine: Engine, capsys: pytest.CaptureFixture[str]) -> None:
    tenant_id, _, expected = _seed_source_rows(postgres_engine)

    rc = ledger_backfill.main(
        [
            "--tenant-id",
            str(tenant_id),
            "--database-url",
            _sync_url(postgres_engine),
            "--dry-run",
        ]
    )
    assert rc == 0
    captured = capsys.readouterr()
    parsed = json.loads(captured.out)
    assert parsed["dry_run"] is True
    assert parsed["planned_counts"] == expected


def test_cli_main_rejects_non_uuid_tenant(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ledger_backfill.main(["--tenant-id", "not-a-uuid", "--database-url", "postgresql://x"])
    assert rc == 2
    assert "must be a UUID" in capsys.readouterr().err
