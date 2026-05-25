"""Unit tests for the matrix snapshot builder — serialization shape + counts."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from control_plane.domain.canonical_memory.matrix import MatrixEdge, MatrixNode
from control_plane.snapshots.builder import build_matrix_snapshot


def _make_node(
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    title: str,
    node_type: str = "stakeholder",
    evidence: list[uuid.UUID] | None = None,
) -> MatrixNode:
    node = MatrixNode()
    node.id = uuid.uuid4()
    node.tenant_id = tenant_id
    node.engagement_id = engagement_id
    node.node_type = node_type
    node.title = title
    node.identity_node_id = None
    node.attributes = {"k": "v"}
    node.status = None
    node.evidence_event_ids = evidence or []
    node.created_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    node.updated_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    return node


def _make_edge(
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    from_id: uuid.UUID,
    to_id: uuid.UUID,
    edge_type: str = "depends_on",
) -> MatrixEdge:
    edge = MatrixEdge()
    edge.id = uuid.uuid4()
    edge.tenant_id = tenant_id
    edge.engagement_id = engagement_id
    edge.edge_type = edge_type
    edge.from_node_id = from_id
    edge.to_node_id = to_id
    edge.attributes = {}
    edge.evidence_event_ids = []
    edge.created_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    edge.updated_at = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    return edge


def _scalars_result(rows: list[object]) -> MagicMock:
    scalars = MagicMock()
    scalars.all.return_value = rows
    result = MagicMock()
    result.scalars.return_value = scalars
    return result


@pytest.mark.asyncio
async def test_builder_serializes_nodes_and_edges_with_matching_counts() -> None:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    n1 = _make_node(tenant_id=tid, engagement_id=eid, title="Alice")
    n2 = _make_node(tenant_id=tid, engagement_id=eid, title="Bob", node_type="organization")
    e1 = _make_edge(tenant_id=tid, engagement_id=eid, from_id=n1.id, to_id=n2.id)

    session = AsyncMock()
    session.execute.side_effect = [_scalars_result([n1, n2]), _scalars_result([e1])]

    nodes, edges = await build_matrix_snapshot(session, tenant_id=tid, engagement_id=eid)

    assert len(nodes) == 2
    assert len(edges) == 1
    assert {n["title"] for n in nodes} == {"Alice", "Bob"}
    assert {n["node_type"] for n in nodes} == {"stakeholder", "organization"}
    assert nodes[0]["attributes"] == {"k": "v"}
    assert nodes[0]["evidence_event_ids"] == []
    assert nodes[0]["created_at"] == "2026-06-01T12:00:00+00:00"

    assert edges[0]["edge_type"] == "depends_on"
    assert edges[0]["from_node_id"] == str(n1.id)
    assert edges[0]["to_node_id"] == str(n2.id)


@pytest.mark.asyncio
async def test_builder_returns_empty_when_no_matrix() -> None:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    session = AsyncMock()
    session.execute.side_effect = [_scalars_result([]), _scalars_result([])]

    nodes, edges = await build_matrix_snapshot(session, tenant_id=tid, engagement_id=eid)

    assert nodes == []
    assert edges == []


@pytest.mark.asyncio
async def test_builder_serializes_uuid_evidence_as_strings() -> None:
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    ev = uuid.uuid4()
    node = _make_node(tenant_id=tid, engagement_id=eid, title="x", evidence=[ev])
    session = AsyncMock()
    session.execute.side_effect = [_scalars_result([node]), _scalars_result([])]

    nodes, _ = await build_matrix_snapshot(session, tenant_id=tid, engagement_id=eid)
    assert nodes[0]["evidence_event_ids"] == [str(ev)]
