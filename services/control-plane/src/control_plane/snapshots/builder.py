"""Serialize an engagement's matrix nodes + edges into snapshot-shaped dicts."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.canonical_memory.matrix import MatrixEdge, MatrixNode


def _node_to_dict(node: MatrixNode) -> dict[str, Any]:
    return {
        "id": str(node.id),
        "node_type": node.node_type,
        "title": node.title,
        "identity_node_id": str(node.identity_node_id) if node.identity_node_id else None,
        "attributes": node.attributes,
        "status": node.status,
        "evidence_event_ids": [str(eid) for eid in node.evidence_event_ids],
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
    }


def _edge_to_dict(edge: MatrixEdge) -> dict[str, Any]:
    return {
        "id": str(edge.id),
        "edge_type": edge.edge_type,
        "from_node_id": str(edge.from_node_id),
        "to_node_id": str(edge.to_node_id),
        "attributes": edge.attributes,
        "evidence_event_ids": [str(eid) for eid in edge.evidence_event_ids],
        "created_at": edge.created_at.isoformat() if edge.created_at else None,
        "updated_at": edge.updated_at.isoformat() if edge.updated_at else None,
    }


async def build_matrix_snapshot(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return ``(nodes, edges)`` as plain dicts for one engagement's matrix."""
    node_rows = (
        (
            await session.execute(
                select(MatrixNode)
                .where(MatrixNode.tenant_id == tenant_id, MatrixNode.engagement_id == engagement_id)
                .order_by(MatrixNode.created_at, MatrixNode.id)
            )
        )
        .scalars()
        .all()
    )
    edge_rows = (
        (
            await session.execute(
                select(MatrixEdge)
                .where(MatrixEdge.tenant_id == tenant_id, MatrixEdge.engagement_id == engagement_id)
                .order_by(MatrixEdge.created_at, MatrixEdge.id)
            )
        )
        .scalars()
        .all()
    )
    return [_node_to_dict(n) for n in node_rows], [_edge_to_dict(e) for e in edge_rows]


__all__ = ["build_matrix_snapshot"]
