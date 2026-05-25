"""Unit tests for :func:`gather_engagement` — mocked session."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.domain.canonical_memory.matrix import MatrixEdge, MatrixInsight, MatrixNode
from control_plane.domain.engagement import Engagement, EngagementMember
from control_plane.domain.strategist_personal import StrategistActivityEvent
from control_plane.exceptions import NotFoundError
from control_plane.export.aggregator import gather_engagement


def _scalar_one_or_none_result(row: object | None) -> MagicMock:
    r = MagicMock()
    r.scalar_one_or_none.return_value = row
    return r


def _scalars_all_result(rows: list[object]) -> MagicMock:
    r = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = rows
    r.scalars.return_value = scalars
    return r


@pytest.mark.asyncio
async def test_raises_not_found_when_engagement_missing() -> None:
    session = AsyncMock()
    session.execute.return_value = _scalar_one_or_none_result(None)

    with pytest.raises(NotFoundError):
        await gather_engagement(session, uuid.uuid4(), uuid.uuid4())


@pytest.mark.asyncio
async def test_aggregates_full_packet() -> None:
    tenant_id = uuid.uuid4()
    engagement_id = uuid.uuid4()
    now = datetime.now(UTC)

    engagement = Engagement(
        id=engagement_id,
        tenant_id=tenant_id,
        name="Pilot",
        customer_account="Acme",
        current_phase="P2_scoping",
        status="active",
        created_at=now,
        updated_at=now,
    )
    member = EngagementMember(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        user_id=uuid.uuid4(),
        role="deployment_strategist",
        created_at=now,
    )
    node = MatrixNode(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        node_type="stakeholder",
        title="Jane",
        attributes={"k": "v"},
        status=None,
        evidence_event_ids=[],
        created_at=now,
        updated_at=now,
    )
    edge = MatrixEdge(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        edge_type="sponsors",
        from_node_id=node.id,
        to_node_id=uuid.uuid4(),
        attributes={},
        evidence_event_ids=[],
        created_at=now,
        updated_at=now,
    )
    insight = MatrixInsight(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        agent="oracle",
        insight_type="risk",
        severity="high",
        title="Sponsor risk",
        body="VP leaving",
        citation_node_ids=[],
        citation_edge_ids=[],
        citation_event_ids=[],
        dedup_key="dk-1",
        status="open",
        created_at=now,
    )
    activity = StrategistActivityEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        actor_id=uuid.uuid4(),
        category="matrix.node.create",
        summary="Made a node",
        detail={},
        created_at=now,
    )

    session = AsyncMock()
    session.execute.side_effect = [
        _scalar_one_or_none_result(engagement),
        _scalars_all_result([member]),
        _scalars_all_result([node]),
        _scalars_all_result([edge]),
        _scalars_all_result([insight]),
        _scalars_all_result([activity]),
    ]

    data = await gather_engagement(session, tenant_id, engagement_id)

    assert data["engagement"]["id"] == str(engagement_id)
    assert data["engagement"]["name"] == "Pilot"
    assert len(data["members"]) == 1
    assert data["members"][0]["role"] == "deployment_strategist"
    assert len(data["matrix_nodes"]) == 1
    assert data["matrix_nodes"][0]["title"] == "Jane"
    assert len(data["matrix_edges"]) == 1
    assert data["matrix_edges"][0]["edge_type"] == "sponsors"
    assert len(data["insights"]) == 1
    assert data["insights"][0]["title"] == "Sponsor risk"
    assert len(data["recent_activity_events"]) == 1
    assert data["recent_activity_events"][0]["category"] == "matrix.node.create"
