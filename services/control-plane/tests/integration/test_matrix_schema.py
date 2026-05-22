"""Integration tests for the Phase 5 deployment-matrix schema (increment 5.2a).

Covers the new ``matrix_nodes`` / ``matrix_edges`` property-graph tables and
the ``engagement_id`` grain fix on the canonical-memory event log. Run with
``uv run pytest -m integration``.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import Engine, text

pytestmark = pytest.mark.integration


def _seed_engagement(conn: object) -> tuple[uuid.UUID, uuid.UUID]:
    """Insert a tenant + engagement, returning ``(tenant_id, engagement_id)``."""
    tenant_id = uuid.uuid4()
    conn.execute(  # type: ignore[attr-defined]
        text("INSERT INTO app_tenants (id, name) VALUES (:t, 'matrix-test')"),
        {"t": str(tenant_id)},
    )
    engagement_id = conn.execute(  # type: ignore[attr-defined]
        text("INSERT INTO engagements (tenant_id, name) VALUES (:t, 'Matrix test') RETURNING id"),
        {"t": str(tenant_id)},
    ).scalar_one()
    return tenant_id, engagement_id


def test_matrix_node_and_edge_round_trip(postgres_engine: Engine) -> None:
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_engagement(conn)

        node_ids = [
            conn.execute(
                text(
                    """
                    INSERT INTO matrix_nodes (tenant_id, engagement_id, node_type, title)
                    VALUES (:t, :e, :node_type, :title)
                    RETURNING id
                    """
                ),
                {"t": str(tenant_id), "e": str(engagement_id), "node_type": nt, "title": title},
            ).scalar_one()
            for nt, title in (("system", "LiDAR ingest"), ("risk", "Calibration slip"))
        ]

        node = conn.execute(
            text("SELECT node_type, title, attributes, evidence_event_ids, status FROM matrix_nodes WHERE id = :id"),
            {"id": str(node_ids[0])},
        ).one()
        assert node.node_type == "system"
        assert node.title == "LiDAR ingest"
        assert node.attributes == {}  # JSONB server default
        assert node.evidence_event_ids == []  # uuid[] server default
        assert node.status is None

        edge_id = conn.execute(
            text(
                """
                INSERT INTO matrix_edges (tenant_id, engagement_id, edge_type, from_node_id, to_node_id)
                VALUES (:t, :e, :edge_type, :from_id, :to_id)
                RETURNING id
                """
            ),
            {
                "t": str(tenant_id),
                "e": str(engagement_id),
                "edge_type": "threatens",
                "from_id": str(node_ids[1]),
                "to_id": str(node_ids[0]),
            },
        ).scalar_one()

        edge = conn.execute(
            text("SELECT edge_type, from_node_id, to_node_id FROM matrix_edges WHERE id = :id"),
            {"id": str(edge_id)},
        ).one()
        assert edge.edge_type == "threatens"
        assert edge.from_node_id == node_ids[1]
        assert edge.to_node_id == node_ids[0]


def test_canonical_event_carries_engagement_id(postgres_engine: Engine) -> None:
    """The Phase 5 grain fix — a canonical event can be scoped to an engagement."""
    with postgres_engine.begin() as conn:
        tenant_id, engagement_id = _seed_engagement(conn)

        event_id = conn.execute(
            text(
                """
                INSERT INTO canonical_memory_events (tenant_id, engagement_id, event_type, occurred_at)
                VALUES (:t, :e, 'meeting.held', now())
                RETURNING id
                """
            ),
            {"t": str(tenant_id), "e": str(engagement_id)},
        ).scalar_one()

        row = conn.execute(
            text("SELECT engagement_id FROM canonical_memory_events WHERE id = :id"),
            {"id": str(event_id)},
        ).one()
        assert row.engagement_id == engagement_id
