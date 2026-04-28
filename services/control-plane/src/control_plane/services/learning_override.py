"""Record strategist overrides against solidified learnings (Epic 10, Stories 10.1-10.2, 10.5-10.7)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.learnings import (
    LearningLifecycleState,
    LearningState,
    SolidifiedLearning,
)
from control_plane.domain.canonical_memory.override_payload import (
    OVERRIDE_EVENT_TYPE,
    OverrideEventPayloadV1,
)
from control_plane.domain.strategist_personal import PrivateOverrideAnnotation
from control_plane.services.private_override_crypto import seal_private_annotation_plaintext
from control_plane.services.strategist_activity import append_strategist_activity


class LearningOverrideError(ValueError):
    """Invalid override request (tenant mismatch, bad evidence, lifecycle)."""


_MIN_WHY_LEN = 20


def _normalize_reason(
    *,
    what_changed: str | None,
    why: str | None,
    reason_string: str | None,
) -> tuple[str, str | None, str | None]:
    if what_changed is not None and why is not None:
        wc, wy = what_changed.strip(), why.strip()
        if not wc:
            raise LearningOverrideError("what_changed required")
        if len(wy) < _MIN_WHY_LEN:
            raise LearningOverrideError(f"why must be at least {_MIN_WHY_LEN} characters")
        return f"{wc}\n\n{wy}", wc, wy
    if reason_string is None or not reason_string.strip():
        raise LearningOverrideError("reason_string required (or provide what_changed + why)")
    rs = reason_string.strip()
    return rs, None, None


async def record_learning_override(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    learning_id: uuid.UUID,
    override_evidence_event_ids: list[uuid.UUID],
    reason_string: str | None = None,
    what_changed: str | None = None,
    why: str | None = None,
    occurred_at: datetime | None = None,
    rfc3161_tsa_token: bytes | None = None,
    private_annotation_plaintext: str | None = None,
    log_activity: bool = True,
) -> uuid.UUID:
    """Insert an append-only override event and transition the learning to ``overridden``.

    Commits the session on success (matches :func:`apply_classification`).

    Returns the new canonical event id (also ``override_id`` in the payload).
    """
    if not override_evidence_event_ids:
        raise LearningOverrideError("override_evidence_event_ids must be non-empty")

    trimmed_reason, wc_opt, wy_opt = _normalize_reason(
        what_changed=what_changed,
        why=why,
        reason_string=reason_string,
    )

    learning = await session.get(SolidifiedLearning, learning_id)
    if learning is None or learning.tenant_id != tenant_id:
        raise LearningOverrideError("learning not found")
    if learning.state in (LearningState.TOMBSTONED, LearningState.OVERRIDDEN):
        raise LearningOverrideError("learning cannot be overridden in its current state")

    for eid in override_evidence_event_ids:
        ev = await session.get(CanonicalMemoryEvent, eid)
        if ev is None or ev.tenant_id != tenant_id:
            raise LearningOverrideError("evidence event not found for tenant")

    when = occurred_at or datetime.now(tz=UTC)
    new_event_id = await session.scalar(text("SELECT deployai_uuid_v7()"))
    if new_event_id is None:
        raise LearningOverrideError("failed to allocate canonical event id")
    payload_model = OverrideEventPayloadV1.build(
        override_id=new_event_id,
        user_id=user_id,
        learning_id=learning_id,
        override_evidence_event_ids=list(override_evidence_event_ids),
        reason_string=trimmed_reason,
        what_changed=wc_opt,
        why=wy_opt,
        occurred_at=when,
        rfc3161_tsa_token=rfc3161_tsa_token,
    )
    override_row = CanonicalMemoryEvent(
        id=new_event_id,
        tenant_id=tenant_id,
        event_type=OVERRIDE_EVENT_TYPE,
        occurred_at=when,
        payload=payload_model.model_dump(mode="json"),
    )
    session.add(override_row)
    await session.flush()

    learning.state = LearningState.OVERRIDDEN
    learning.supersession_override_event_id = override_row.id
    learning.superseding_evidence_event_ids = list(override_evidence_event_ids)

    session.add(
        LearningLifecycleState(
            tenant_id=tenant_id,
            learning_id=learning_id,
            state=LearningState.OVERRIDDEN,
            transitioned_at=when,
            actor_id=user_id,
            reason=trimmed_reason,
        )
    )

    note = (private_annotation_plaintext or "").strip()
    if note:
        nonce, ct, wrapped = seal_private_annotation_plaintext(tenant_id=tenant_id, plaintext=note)
        session.add(
            PrivateOverrideAnnotation(
                tenant_id=tenant_id,
                override_event_id=override_row.id,
                author_actor_id=user_id,
                nonce=nonce,
                ciphertext=ct,
                wrapped_dek=wrapped,
            )
        )

    if log_activity:
        await append_strategist_activity(
            session,
            tenant_id=tenant_id,
            actor_id=user_id,
            category="override_submitted",
            summary="Learning override submitted",
            detail={
                "learning_id": str(learning_id),
                "override_event_id": str(override_row.id),
                "evidence_count": len(override_evidence_event_ids),
            },
            ref_id=override_row.id,
        )

    await session.commit()
    return override_row.id
