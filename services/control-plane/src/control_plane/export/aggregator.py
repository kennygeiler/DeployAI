"""Pull every packet-relevant row for one engagement into a single dict."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.canonical_memory.matrix import (
    MatrixEdge,
    MatrixInsight,
    MatrixNode,
)
from control_plane.domain.engagement import Engagement, EngagementMember
from control_plane.domain.strategist_personal import StrategistActivityEvent
from control_plane.exceptions import NotFoundError


async def gather_engagement(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> dict[str, Any]:
    engagement = (
        await session.execute(
            select(Engagement).where(
                Engagement.id == engagement_id,
                Engagement.tenant_id == tenant_id,
            )
        )
    ).scalar_one_or_none()
    if engagement is None:
        raise NotFoundError(f"engagement {engagement_id} not found for tenant {tenant_id}")

    members = (
        (
            await session.execute(
                select(EngagementMember)
                .where(
                    EngagementMember.tenant_id == tenant_id,
                    EngagementMember.engagement_id == engagement_id,
                )
                .order_by(EngagementMember.created_at)
            )
        )
        .scalars()
        .all()
    )

    nodes = (
        (
            await session.execute(
                select(MatrixNode)
                .where(
                    MatrixNode.tenant_id == tenant_id,
                    MatrixNode.engagement_id == engagement_id,
                )
                .order_by(MatrixNode.created_at)
            )
        )
        .scalars()
        .all()
    )

    edges = (
        (
            await session.execute(
                select(MatrixEdge)
                .where(
                    MatrixEdge.tenant_id == tenant_id,
                    MatrixEdge.engagement_id == engagement_id,
                )
                .order_by(MatrixEdge.created_at)
            )
        )
        .scalars()
        .all()
    )

    insights = (
        (
            await session.execute(
                select(MatrixInsight)
                .where(
                    MatrixInsight.tenant_id == tenant_id,
                    MatrixInsight.engagement_id == engagement_id,
                )
                .order_by(MatrixInsight.created_at)
            )
        )
        .scalars()
        .all()
    )

    activity = (
        (
            await session.execute(
                select(StrategistActivityEvent)
                .where(StrategistActivityEvent.tenant_id == tenant_id)
                .order_by(StrategistActivityEvent.created_at.desc())
                .limit(100)
            )
        )
        .scalars()
        .all()
    )

    return {
        "engagement": {
            "id": str(engagement.id),
            "name": engagement.name,
            "customer_account": engagement.customer_account,
            "current_phase": engagement.current_phase,
            "created_at": engagement.created_at.isoformat() if engagement.created_at else None,
        },
        "members": [
            {
                "id": str(m.id),
                "user_id": str(m.user_id),
                "role": m.role,
            }
            for m in members
        ],
        "matrix_nodes": [
            {
                "id": str(n.id),
                "node_type": n.node_type,
                "title": n.title,
                "status": n.status,
                "attributes": n.attributes,
            }
            for n in nodes
        ],
        "matrix_edges": [
            {
                "id": str(e.id),
                "edge_type": e.edge_type,
                "from_node_id": str(e.from_node_id),
                "to_node_id": str(e.to_node_id),
                "attributes": e.attributes,
            }
            for e in edges
        ],
        "insights": [
            {
                "id": str(i.id),
                "agent": i.agent,
                "insight_type": i.insight_type,
                "severity": i.severity,
                "title": i.title,
                "body": i.body,
                "status": i.status,
            }
            for i in insights
        ],
        "recent_activity_events": [
            {
                "id": str(a.id),
                "actor_id": str(a.actor_id),
                "category": a.category,
                "summary": a.summary,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in activity
        ],
    }
