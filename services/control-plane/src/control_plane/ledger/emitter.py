"""Single entry point for appending rows onto ``ledger_events``.

See ``docs/design/timeline-ledger.md`` §4 — the caller (route handler or
service helper) owns the surrounding transaction. ``emit_ledger_event``
does ``session.add`` + ``flush`` only so a rollback drops the ledger row
in lockstep with whatever state change provoked it.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.ledger import (
    LedgerEvent,
    LedgerEventAffects,
    LedgerEventCause,
)

ALLOWED_SOURCE_KINDS: frozenset[str] = frozenset(
    {
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
        "oracle_chat_turn",
        "oracle_conversation_started",
        "user_provisioned",
        "audit_decision",
        "insight_snoozed",
        "followup_task_created",
        # v2 Phase 0.5 — compounding synthesis layer (scope-v2 §3).
        "agent_synthesis_emitted",
        "synthesis_failed",
        "synthesis_validation_failed",
        "synthesis_stale_flagged",
    }
)

ALLOWED_AFFECT_KINDS: frozenset[str] = frozenset(
    {"matrix_node", "matrix_edge", "insight", "recommendation", "app_user"}
)

_SUMMARY_MIN = 1
_SUMMARY_MAX = 500

# Detail keys we never want to land in the ledger — same posture as the
# audit emit hygiene rule (see timeline-ledger.md §9.2).
_SECRET_KEY_NEEDLES: tuple[str, ...] = (
    "api_key",
    "apikey",
    "signing_secret",
    "client_secret",
    "secret",
    "webhook_url",
    "bearer_token",
    "access_token",
    "refresh_token",
    "password",
    "private_key",
)

AffectsEntry = tuple[str, uuid.UUID]


async def emit_ledger_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    occurred_at: datetime,
    actor_kind: str,
    actor_id: str | None,
    source_kind: str,
    source_ref: uuid.UUID | None,
    summary: str,
    detail: dict[str, Any],
    caused_by: Iterable[uuid.UUID] = (),
    affects: Iterable[AffectsEntry] = (),
) -> LedgerEvent:
    """Append one ledger row plus its cause / affect edges in a single flush.

    Caller commits. Validates ``source_kind`` against the enum from design §3.1
    and strips secret-shaped keys from ``detail`` defensively.
    """
    if source_kind not in ALLOWED_SOURCE_KINDS:
        raise ValueError(f"invalid source_kind: {source_kind!r}")
    if not isinstance(summary, str) or not (_SUMMARY_MIN <= len(summary) <= _SUMMARY_MAX):
        raise ValueError(f"summary length must be between {_SUMMARY_MIN} and {_SUMMARY_MAX} characters")
    if not isinstance(actor_kind, str) or not actor_kind:
        raise ValueError("actor_kind must be a non-empty string")
    if not isinstance(detail, dict):
        raise ValueError("detail must be a dict")

    affects_list = list(affects)
    sanitised = _scrub_secrets(detail)

    row = LedgerEvent(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=occurred_at,
        actor_kind=actor_kind,
        actor_id=actor_id,
        source_kind=source_kind,
        source_ref=source_ref,
        summary=summary,
        detail=sanitised,
    )
    session.add(row)
    await session.flush()

    for parent_id in caused_by:
        if parent_id == row.id:
            continue  # self-cause is a schema CHECK; skip defensively
        session.add(LedgerEventCause(event_id=row.id, caused_by_id=parent_id))

    for entity_kind, entity_id in affects_list:
        if entity_kind not in ALLOWED_AFFECT_KINDS:
            raise ValueError(f"invalid affect entity_kind: {entity_kind!r}")
        session.add(LedgerEventAffects(event_id=row.id, entity_kind=entity_kind, entity_id=entity_id))

    if caused_by or affects_list:
        await session.flush()

    if engagement_id is not None:
        await _maybe_enqueue_synthesis(
            session,
            event=row,
            engagement_id=engagement_id,
            affects=affects_list,
            detail=sanitised,
        )
    return row


async def _maybe_enqueue_synthesis(
    session: AsyncSession,
    *,
    event: LedgerEvent,
    engagement_id: uuid.UUID,
    affects: list[AffectsEntry],
    detail: dict[str, Any],
) -> None:
    """Insert one ``synthesis_refresh_jobs`` row per synthesis trigger.

    Routing rules per scope-v2 §3.2:
      - ``proposal_accepted`` whose ``detail.node_type == 'decision'`` and that
        ``affects`` a matrix_node → ``decision_provenance`` job on that node.
      - ``insight_opened`` with ``detail.severity == 'high'`` and an
        ``affects`` insight → ``risk_explainer`` job on that insight.
      - ``matrix_node_created`` whose ``detail.node_type == 'stakeholder'`` or
        ``member_added`` that affects a stakeholder node → ``stakeholder_brief``.

    For ``proposal_accepted`` the preferred path is the explicit
    ``detail.node_type`` hint set by the accept route. As a defensive fallback,
    if the hint is missing but the event affects a matrix_node, the dispatcher
    looks up ``node_type`` from ``matrix_nodes`` so older / future emit sites
    that forget the hint still drive the right refresh job.

    Local import keeps the emitter module free of ORM-cycle risk (the
    synthesis ORM lives in ``canonical_memory``, which already imports the
    ledger ORM transitively).
    """
    from control_plane.domain.canonical_memory.matrix import MatrixNode, SynthesisRefreshJob

    triggers: list[tuple[str, uuid.UUID]] = []
    src = event.source_kind
    if src == "proposal_accepted":
        hint = detail.get("node_type")
        node_type: str | None = hint if isinstance(hint, str) else None
        affected_nodes = [tid for kind, tid in affects if kind == "matrix_node"]
        if node_type is None and affected_nodes:
            node_type = await _lookup_matrix_node_type(session, MatrixNode, affected_nodes[0])
        if node_type == "decision":
            for target_id in affected_nodes:
                triggers.append(("decision_provenance", target_id))
    elif src == "insight_opened" and detail.get("severity") == "high":
        for kind, target_id in affects:
            if kind == "insight":
                triggers.append(("risk_explainer", target_id))
    elif src == "matrix_node_created" and detail.get("node_type") == "stakeholder":
        for kind, target_id in affects:
            if kind == "matrix_node":
                triggers.append(("stakeholder_brief", target_id))
    elif src == "member_added":
        # member_added does not always carry a stakeholder node id in affects;
        # only enqueue when the route explicitly hints at one.
        stakeholder_node_id = detail.get("stakeholder_node_id")
        if isinstance(stakeholder_node_id, str):
            try:
                triggers.append(("stakeholder_brief", uuid.UUID(stakeholder_node_id)))
            except ValueError:
                pass

    for job_kind, target_id in triggers:
        session.add(
            SynthesisRefreshJob(
                tenant_id=event.tenant_id,
                engagement_id=engagement_id,
                kind=job_kind,
                target_id=target_id,
                trigger_event_id=event.id,
            )
        )
    if triggers:
        await session.flush()


async def _lookup_matrix_node_type(
    session: AsyncSession,
    matrix_node_cls: Any,
    node_id: uuid.UUID,
) -> str | None:
    """Look up ``node_type`` for one matrix_node id, or ``None`` if absent.

    Fallback for ``proposal_accepted`` emit sites that did not populate the
    ``detail.node_type`` hint — see ``_maybe_enqueue_synthesis``.
    """
    node = await session.get(matrix_node_cls, node_id)
    if node is None:
        return None
    value = node.node_type
    return value if isinstance(value, str) else None


def _scrub_secrets(detail: dict[str, Any]) -> dict[str, Any]:
    """Return a shallow copy of ``detail`` with secret-shaped keys removed.

    Recurses one level into nested dicts and into lists of dicts so callers
    that nest under ``connection`` / ``config`` don't leak through.
    """
    cleaned: dict[str, Any] = {}
    for key, value in detail.items():
        if _looks_secret(key):
            continue
        if isinstance(value, dict):
            cleaned[key] = _scrub_secrets(value)
        elif isinstance(value, list):
            cleaned[key] = [_scrub_secrets(item) if isinstance(item, dict) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


def _looks_secret(key: str) -> bool:
    needle = key.lower()
    return any(token in needle for token in _SECRET_KEY_NEEDLES)
