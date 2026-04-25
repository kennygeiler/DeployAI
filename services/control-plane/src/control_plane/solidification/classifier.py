"""Tiered solidification (Epic 5, Story 5.5, FR28)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.canonical_memory.learnings import (
    LearningLifecycleState,
    LearningState,
    SolidifiedLearning,
)
from control_plane.domain.tenant_phase import SolidificationReviewQueue

Classification = Literal["stay_candidate", "class_A_auto_solidify", "class_B_weekly_review"]

STRUCTURED_SOURCES = frozenset({"scim", "calendar", "m365_meeting", "entra", "gmail_sync"})


def classify_candidate(*, source_kind: str, confidence: float) -> Classification:
    if confidence < 0.6:
        return "stay_candidate"
    sk = source_kind.lower().strip()
    is_structured = any(x in sk for x in STRUCTURED_SOURCES) or sk in STRUCTURED_SOURCES
    if is_structured and confidence >= 0.9:
        return "class_A_auto_solidify"
    if 0.6 <= confidence < 0.9:
        return "class_B_weekly_review"
    if not is_structured and confidence >= 0.9:
        return "class_B_weekly_review"
    return "stay_candidate"


async def apply_classification(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    learning_id: uuid.UUID,
    source_kind: str,
    confidence: float,
) -> Classification:
    """Update ``solidified_learnings`` or enqueue Class B. Returns the classification path taken."""
    kind = classify_candidate(source_kind=source_kind, confidence=confidence)
    if kind == "stay_candidate":
        return kind

    if kind == "class_A_auto_solidify":
        r = await session.get(SolidifiedLearning, learning_id)
        if r is None or r.tenant_id != tenant_id:
            return "stay_candidate"
        r.state = LearningState.SOLIDIFIED
        now = datetime.now(tz=UTC)
        session.add(
            LearningLifecycleState(
                tenant_id=tenant_id,
                learning_id=learning_id,
                state=LearningState.SOLIDIFIED,
                transitioned_at=now,
                reason="class_A_auto_solidify (Epic 5)",
            )
        )
        await session.commit()
        return kind

    if kind == "class_B_weekly_review":
        session.add(
            SolidificationReviewQueue(
                tenant_id=tenant_id,
                learning_id=learning_id,
                status="open",
            )
        )
        await session.commit()
        return kind

    return "stay_candidate"
