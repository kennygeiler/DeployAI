"""Integration: Phase F1.a ledger schema lands cleanly under ``alembic upgrade head``.

Run with ``uv run pytest -m integration``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.integration


def _seed_engagement(conn: object) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    conn.execute(  # type: ignore[attr-defined]
        text("INSERT INTO app_tenants (id, name) VALUES (:t, 'ledger-test')"),
        {"t": str(tenant_id)},
    )
    engagement_id = conn.execute(  # type: ignore[attr-defined]
        text("INSERT INTO engagements (tenant_id, name) VALUES (:t, 'Ledger test') RETURNING id"),
        {"t": str(tenant_id)},
    ).scalar_one()
    return tenant_id, engagement_id


def _insert_event(
    conn: object,
    tenant_id: uuid.UUID,
    *,
    engagement_id: uuid.UUID | None = None,
    occurred_at: datetime | None = None,
    actor_kind: str = "system",
    source_kind: str = "email_ingest",
    source_ref: uuid.UUID | None = None,
    summary: str = "row",
) -> uuid.UUID:
    return conn.execute(  # type: ignore[attr-defined]
        text(
            "INSERT INTO ledger_events "
            "(tenant_id, engagement_id, occurred_at, actor_kind, source_kind, source_ref, summary) "
            "VALUES (:t, :e, :o, :ak, :sk, :sr, :s) RETURNING id"
        ),
        {
            "t": str(tenant_id),
            "e": str(engagement_id) if engagement_id else None,
            "o": occurred_at or datetime.now(UTC),
            "ak": actor_kind,
            "sk": source_kind,
            "sr": str(source_ref) if source_ref else None,
            "s": summary,
        },
    ).scalar_one()


def test_all_four_ledger_tables_exist(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = 'public' AND table_name IN "
                "('ledger_events','ledger_event_causes','ledger_event_affects','temporal_insights')"
            )
        ).all()
    names = {r.table_name for r in rows}
    assert names == {
        "ledger_events",
        "ledger_event_causes",
        "ledger_event_affects",
        "temporal_insights",
    }


def test_expected_indexes_exist_on_ledger_events(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'ledger_events'")
        ).all()
    names = {r.indexname for r in rows}
    expected = {
        "ix_ledger_tenant_occurred",
        "ix_ledger_engagement_occurred",
        "ix_ledger_source_kind",
        "ix_ledger_actor",
        "ix_ledger_detail_gin",
    }
    assert expected.issubset(names), f"missing: {expected - names}"


def test_temporal_insights_indexes_exist(postgres_engine: Engine) -> None:
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text("SELECT indexname FROM pg_indexes WHERE schemaname = 'public' AND tablename = 'temporal_insights'")
        ).all()
    names = {r.indexname for r in rows}
    assert {
        "ix_temporal_tenant_engagement",
        "ix_temporal_kind",
        "ix_temporal_window",
    }.issubset(names)


def test_ledger_event_round_trip(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_engagement(conn)
        event_id = _insert_event(
            conn,
            tenant_id,
            engagement_id=engagement_id,
            actor_kind="agent:matrix_extractor",
            source_kind="llm_proposal_created",
            summary="proposal landed",
        )
        row = conn.execute(
            text(
                "SELECT tenant_id, engagement_id, actor_kind, source_kind, summary, "
                "       detail, recorded_at FROM ledger_events WHERE id = :id"
            ),
            {"id": str(event_id)},
        ).one()
    assert row.tenant_id == tenant_id
    assert row.engagement_id == engagement_id
    assert row.actor_kind == "agent:matrix_extractor"
    assert row.source_kind == "llm_proposal_created"
    assert row.summary == "proposal landed"
    assert row.detail == {}
    assert row.recorded_at is not None


def test_summary_length_constraint_rejects_empty(postgres_engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as conn:
            tenant_id, _ = _seed_engagement(conn)
            _insert_event(conn, tenant_id, summary="")


def test_cause_edge_round_trip_and_self_link_rejected(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_engagement(conn)
        parent = _insert_event(conn, tenant_id, engagement_id=engagement_id, summary="parent")
        child = _insert_event(conn, tenant_id, engagement_id=engagement_id, summary="child")
        conn.execute(
            text("INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES (:c, :p)"),
            {"c": str(child), "p": str(parent)},
        )
        row = conn.execute(
            text("SELECT caused_by_id FROM ledger_event_causes WHERE event_id = :c"),
            {"c": str(child)},
        ).one()
        assert row.caused_by_id == parent

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as conn:
            tenant_id, _ = _seed_engagement(conn)
            ev = _insert_event(conn, tenant_id, summary="self")
            conn.execute(
                text("INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES (:e, :e)"),
                {"e": str(ev)},
            )


def test_cause_cascades_when_parent_event_deleted(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_engagement(conn)
        parent = _insert_event(conn, tenant_id, engagement_id=engagement_id)
        child = _insert_event(conn, tenant_id, engagement_id=engagement_id)
        conn.execute(
            text("INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES (:c, :p)"),
            {"c": str(child), "p": str(parent)},
        )

    with postgres_engine.begin() as conn:
        conn.execute(text("DELETE FROM ledger_events WHERE id = :id"), {"id": str(parent)})

    with postgres_engine.connect() as conn:
        remaining = conn.execute(
            text("SELECT count(*) FROM ledger_event_causes WHERE event_id = :c"),
            {"c": str(child)},
        ).scalar_one()
    assert remaining == 0


def test_affects_polymorphic_round_trip(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_engagement(conn)
        ev = _insert_event(conn, tenant_id, engagement_id=engagement_id)
        node_id = uuid.uuid4()
        insight_id = uuid.uuid4()
        for kind, eid in (("matrix_node", node_id), ("insight", insight_id)):
            conn.execute(
                text("INSERT INTO ledger_event_affects (event_id, entity_kind, entity_id) VALUES (:e, :k, :i)"),
                {"e": str(ev), "k": kind, "i": str(eid)},
            )
        rows = conn.execute(
            text("SELECT entity_kind, entity_id FROM ledger_event_affects WHERE event_id = :e"),
            {"e": str(ev)},
        ).all()
    pairs = {(r.entity_kind, r.entity_id) for r in rows}
    assert pairs == {("matrix_node", node_id), ("insight", insight_id)}


def test_temporal_insight_round_trip_and_window_check(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_engagement(conn)
        now = datetime.now(UTC)
        insight_id = conn.execute(
            text(
                "INSERT INTO temporal_insights "
                "(tenant_id, engagement_id, insight_kind, severity, title, narrative, "
                " window_start, window_end) "
                "VALUES (:t, :e, 'stakeholder_churn', 'high', 'Spike', 'narrative', :ws, :we) "
                "RETURNING id"
            ),
            {
                "t": str(tenant_id),
                "e": str(engagement_id),
                "ws": now - timedelta(days=7),
                "we": now,
            },
        ).scalar_one()
        row = conn.execute(
            text("SELECT severity, status, evidence_event_ids, metrics FROM temporal_insights WHERE id = :id"),
            {"id": str(insight_id)},
        ).one()
    assert row.severity == "high"
    assert row.status == "open"
    assert row.evidence_event_ids == []
    assert row.metrics == {}

    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as conn:
            tenant_id, _ = _seed_engagement(conn)
            conn.execute(
                text(
                    "INSERT INTO temporal_insights "
                    "(tenant_id, insight_kind, severity, title, narrative, "
                    " window_start, window_end) "
                    "VALUES (:t, 'churn', 'high', 't', 'n', :late, :early)"
                ),
                {"t": str(tenant_id), "late": now, "early": now - timedelta(days=1)},
            )


def test_temporal_insight_severity_enum_rejected(postgres_engine: Engine) -> None:
    with pytest.raises(IntegrityError):
        with postgres_engine.begin() as conn:
            tenant_id, _ = _seed_engagement(conn)
            now = datetime.now(UTC)
            conn.execute(
                text(
                    "INSERT INTO temporal_insights "
                    "(tenant_id, insight_kind, severity, title, narrative, "
                    " window_start, window_end) "
                    "VALUES (:t, 'churn', 'bogus', 't', 'n', :ws, :we)"
                ),
                {"t": str(tenant_id), "ws": now, "we": now},
            )
