"""Compounding-synthesis workers (v2 Phase 0.5, scope-v2 §3.2).

Three refresh entrypoints — one per synthesis kind — each tenant + engagement
scoped, each calling the tenant-resolved LLM provider for structured JSON
output that lists per-paragraph citations. Output is validated by the
claim-cite module before persistence; failures emit ledger events instead of
corrupting the curated substrate.

Triggered indirectly: a route lands a ``proposal_accepted`` / ``insight_opened`` /
``matrix_node_created`` event via ``emit_ledger_event``, the emitter inserts a
``synthesis_refresh_jobs`` row, and ``POST /internal/v1/admin/synthesis/drain``
calls these functions to drain the queue. Phase 0.6 swaps the manual drain
for a cron worker; the function signatures here will not change.
"""

from __future__ import annotations

import copy
import json
import logging
import uuid
from collections import deque
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.llm import get_llm_provider, resolve_tenant_llm_provider
from control_plane.agents.synthesis.claim_cite import (
    Citation,
    validate_per_claim_cites,
    verify_citations_exist,
)
from control_plane.domain.canonical_memory.matrix import (
    MatrixInsight,
    MatrixNode,
)
from control_plane.domain.ledger import LedgerEvent, LedgerEventCause
from control_plane.intelligence.budget import check_and_charge
from control_plane.ledger import emit_ledger_event

_log = logging.getLogger(__name__)

_SYNTHESIS_TOKEN_ESTIMATE = 800
_LLM_MAX_OUTPUT_TOKENS = 600
_LLM_TEMPERATURE = 0.2
_CHAIN_MAX_DEPTH = 4
_CHAIN_MAX_NODES = 20
_MAX_RETRIES = 1


# ---------------------------------------------------------------------------
# Public entrypoints
# ---------------------------------------------------------------------------


async def refresh_decision_provenance(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    decision_node_id: uuid.UUID,
    now: datetime,
    trigger_event_id: uuid.UUID | None = None,
) -> MatrixInsight | None:
    """Refresh ``kenny:decision_provenance:{node}`` synthesis for one decision.

    Walks the upstream causal chain from the most recent ``proposal_accepted``
    event affecting the decision node, asks the LLM for a per-paragraph cited
    summary, validates citations against the ledger in this engagement, then
    upserts a ``matrix_insights`` row with ``agent='kenny'``. Returns ``None``
    when the synthesis cannot be produced (missing trigger event, budget
    exhausted, persistent validation failure).
    """
    node = await _require_matrix_node(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        node_id=decision_node_id,
    )
    if node is None:
        return None
    anchor = await _find_anchor_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        target_kind="matrix_node",
        target_id=decision_node_id,
        source_kind="proposal_accepted",
        preferred_event_id=trigger_event_id,
    )
    if anchor is None:
        return None
    chain = await _walk_causal_chain(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        root_event_id=anchor.id,
    )
    prompt_context = _format_chain_context(
        title=f"Decision: {node.title}",
        anchor=anchor,
        chain=chain,
    )
    instructions = (
        "Summarize WHY this decision exists, grounded only in the supplied events. "
        "Reply ONLY with JSON of shape "
        '{"title": str, "body": str, "claim_citations": [{"paragraph": int, '
        '"event_ids": [uuid_str, ...]}]}. '
        "The body MUST be 2-4 short paragraphs separated by blank lines and EVERY "
        "paragraph MUST embed at least one inline citation tag formatted exactly as "
        "[event:UUID] referencing the supplied event ids. Do not invent ids."
    )

    return await _run_insight_synthesis(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        kind="decision_provenance",
        target_id=decision_node_id,
        anchor=anchor,
        prompt_context=prompt_context,
        instructions=instructions,
        insight_type="decision_provenance_summary",
        dedup_key=f"kenny:decision_provenance:{decision_node_id}",
        citation_node_ids=[decision_node_id],
        now=now,
    )


async def refresh_risk_explainer(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    risk_insight_id: uuid.UUID,
    now: datetime,
    trigger_event_id: uuid.UUID | None = None,
) -> MatrixInsight | None:
    """Refresh ``kenny:risk_explainer:{insight}`` for an open high-severity risk."""
    risk = await _require_matrix_insight(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        insight_id=risk_insight_id,
    )
    if risk is None:
        return None
    anchor = await _find_anchor_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        target_kind="insight",
        target_id=risk_insight_id,
        source_kind="insight_opened",
        preferred_event_id=trigger_event_id,
    )
    if anchor is None:
        return None
    chain = await _walk_causal_chain(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        root_event_id=anchor.id,
    )
    prompt_context = _format_chain_context(
        title=f"Risk: {risk.title} (severity={risk.severity})",
        anchor=anchor,
        chain=chain,
        extra=risk.body,
    )
    instructions = (
        "Summarize WHY this risk is open and WHAT evidence supports it, grounded only "
        "in the supplied events and the originating insight body. "
        "Reply ONLY with JSON of shape "
        '{"title": str, "body": str, "claim_citations": [{"paragraph": int, '
        '"event_ids": [uuid_str, ...]}]}. '
        "Body MUST be 2-4 paragraphs separated by blank lines and EVERY paragraph MUST "
        "embed at least one [event:UUID] cite tag using only the supplied event ids."
    )

    return await _run_insight_synthesis(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        kind="risk_explainer",
        target_id=risk_insight_id,
        anchor=anchor,
        prompt_context=prompt_context,
        instructions=instructions,
        insight_type="risk_explainer",
        dedup_key=f"kenny:risk_explainer:{risk_insight_id}",
        citation_node_ids=list(risk.citation_node_ids or ()),
        now=now,
    )


async def refresh_stakeholder_brief(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    stakeholder_node_id: uuid.UUID,
    now: datetime,
    trigger_event_id: uuid.UUID | None = None,
) -> MatrixNode | None:
    """Refresh ``attributes.description`` on a stakeholder matrix node.

    Unlike the other two entrypoints this writes into the node's existing
    JSONB ``attributes`` blob (not a new column, not a new matrix_insights row)
    so the stakeholder *page* itself carries cited prose. Emits an
    ``agent_synthesis_emitted`` ledger event for audit.
    """
    node = await _require_matrix_node(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        node_id=stakeholder_node_id,
    )
    if node is None or node.node_type != "stakeholder":
        return None
    anchor = await _find_anchor_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        target_kind="matrix_node",
        target_id=stakeholder_node_id,
        source_kind=None,
        preferred_event_id=trigger_event_id,
    )
    if anchor is None:
        return None
    chain = await _walk_causal_chain(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        root_event_id=anchor.id,
    )
    prompt_context = _format_chain_context(
        title=f"Stakeholder: {node.title}",
        anchor=anchor,
        chain=chain,
        extra=_node_attributes_summary(node),
    )
    instructions = (
        "Draft a 2-3 paragraph brief describing this stakeholder's role and "
        "relationships, grounded only in the supplied events. "
        "Reply ONLY with JSON of shape "
        '{"title": str, "body": str, "claim_citations": [{"paragraph": int, '
        '"event_ids": [uuid_str, ...]}]}. '
        "EVERY paragraph in body MUST embed at least one [event:UUID] tag."
    )

    env_fallback = get_llm_provider()
    provider = await resolve_tenant_llm_provider(session, tenant_id, env_fallback)
    granted = await check_and_charge(session, tenant_id=tenant_id, estimate=_SYNTHESIS_TOKEN_ESTIMATE)
    if not granted:
        await _emit_failure(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            now=now,
            kind="stakeholder_brief",
            target_id=stakeholder_node_id,
            anchor_id=anchor.id,
            reason="budget_exhausted",
        )
        return None

    drafted = await _phrase_and_validate(
        session,
        provider=provider,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        prompt_context=prompt_context,
        instructions=instructions,
    )
    if drafted is None:
        await _emit_failure(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            now=now,
            kind="stakeholder_brief",
            target_id=stakeholder_node_id,
            anchor_id=anchor.id,
            reason="validation_failed",
            validation=True,
        )
        return None

    body_text, citations, source_event_ids = drafted

    # Mutate attributes in-place. JSONB assignment requires a fresh object so
    # SQLAlchemy treats the column as dirty; copy-then-set preserves whatever
    # the extractor put there previously.
    new_attrs: dict[str, Any] = copy.deepcopy(node.attributes or {})
    new_attrs["description"] = body_text
    new_attrs["description_source_event_ids"] = [str(eid) for eid in source_event_ids]
    new_attrs["description_refreshed_at"] = now.isoformat()
    node.attributes = new_attrs
    await session.flush()

    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=now,
        actor_kind="agent:kenny",
        actor_id="synthesizer",
        source_kind="agent_synthesis_emitted",
        source_ref=stakeholder_node_id,
        summary=f"Stakeholder brief refreshed for {node.title}"[:500],
        detail={
            "kind": "stakeholder_brief",
            "node_id": str(stakeholder_node_id),
            "citation_count": len(citations),
            "source_event_ids": [str(eid) for eid in source_event_ids],
        },
        caused_by=[anchor.id],
        affects=[("matrix_node", stakeholder_node_id)],
    )
    return node


# ---------------------------------------------------------------------------
# Stale-flag helper (used by lint worker / integration tests).
# ---------------------------------------------------------------------------


async def mark_stale_for_deleted_sources(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    now: datetime,
) -> list[uuid.UUID]:
    """Mark every synthesized insight in scope whose ``source_event_ids``
    references at least one event that no longer exists. Returns the affected
    insight ids. Phase 0.6 will host this on the lint worker; we expose it
    here so integration tests can exercise the stale path before that lands.
    """
    stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tenant_id,
        MatrixInsight.engagement_id == engagement_id,
        MatrixInsight.agent.in_(("kenny", "oracle")),
        MatrixInsight.stale.is_(False),
    )
    rows = list((await session.execute(stmt)).scalars().all())
    if not rows:
        return []
    all_ids: set[uuid.UUID] = set()
    for row in rows:
        all_ids.update(row.citation_event_ids or ())
    if not all_ids:
        return []
    existing_q = await session.execute(select(LedgerEvent.id).where(LedgerEvent.id.in_(all_ids)))
    existing = set(existing_q.scalars().all())
    flagged: list[uuid.UUID] = []
    for row in rows:
        missing = [eid for eid in (row.citation_event_ids or ()) if eid not in existing]
        if missing:
            row.stale = True
            flagged.append(row.id)
            await emit_ledger_event(
                session,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                occurred_at=now,
                actor_kind="agent:kenny",
                actor_id="synthesizer",
                source_kind="synthesis_stale_flagged",
                source_ref=row.id,
                summary=f"Synthesis stale: {row.title[:100]}"[:500],
                detail={
                    "insight_id": str(row.id),
                    "missing_event_ids": [str(eid) for eid in missing],
                },
                affects=[("insight", row.id)],
            )
    if flagged:
        await session.flush()
    return flagged


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _run_insight_synthesis(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    kind: str,
    target_id: uuid.UUID,
    anchor: LedgerEvent,
    prompt_context: str,
    instructions: str,
    insight_type: str,
    dedup_key: str,
    citation_node_ids: list[uuid.UUID],
    now: datetime,
) -> MatrixInsight | None:
    env_fallback = get_llm_provider()
    provider = await resolve_tenant_llm_provider(session, tenant_id, env_fallback)
    granted = await check_and_charge(session, tenant_id=tenant_id, estimate=_SYNTHESIS_TOKEN_ESTIMATE)
    if not granted:
        await _emit_failure(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            now=now,
            kind=kind,
            target_id=target_id,
            anchor_id=anchor.id,
            reason="budget_exhausted",
        )
        return None

    drafted = await _phrase_and_validate(
        session,
        provider=provider,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        prompt_context=prompt_context,
        instructions=instructions,
    )
    if drafted is None:
        await _emit_failure(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            now=now,
            kind=kind,
            target_id=target_id,
            anchor_id=anchor.id,
            reason="validation_failed",
            validation=True,
        )
        return None
    body_text, citations, source_event_ids = drafted

    existing_q = await session.execute(
        select(MatrixInsight).where(
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.dedup_key == dedup_key,
        )
    )
    existing = existing_q.scalar_one_or_none()
    title = _derive_title(anchor=anchor, kind=kind)
    if existing is None:
        row = MatrixInsight(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            agent="kenny",
            insight_type=insight_type,
            severity="medium",
            title=title,
            body=body_text,
            citation_node_ids=list(citation_node_ids),
            citation_edge_ids=[],
            citation_event_ids=list(source_event_ids),
            dedup_key=dedup_key,
            status="open",
            input_hash=None,
            last_refreshed_at=now,
            stale=False,
        )
        session.add(row)
        await session.flush()
        result = row
    else:
        existing.title = title
        existing.body = body_text
        existing.citation_node_ids = list(citation_node_ids)
        existing.citation_event_ids = list(source_event_ids)
        existing.last_refreshed_at = now
        existing.stale = False
        if existing.status == "resolved":
            existing.status = "open"
            existing.decided_at = None
            existing.decided_by = None
        await session.flush()
        result = existing

    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=now,
        actor_kind="agent:kenny",
        actor_id="synthesizer",
        source_kind="agent_synthesis_emitted",
        source_ref=result.id,
        summary=f"{kind} synthesis emitted: {title[:120]}"[:500],
        detail={
            "kind": kind,
            "insight_id": str(result.id),
            "target_id": str(target_id),
            "citation_count": len(citations),
            "source_event_ids": [str(eid) for eid in source_event_ids],
        },
        caused_by=[anchor.id],
        affects=[("insight", result.id)],
    )
    return result


async def _phrase_and_validate(
    session: AsyncSession,
    *,
    provider: Any,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    prompt_context: str,
    instructions: str,
) -> tuple[str, list[Citation], list[uuid.UUID]] | None:
    """Call the LLM up to ``1 + _MAX_RETRIES`` times, returning ``(body, cites, ids)``
    on success or ``None`` after persistent validation failure / LLM error.
    """
    for attempt in range(_MAX_RETRIES + 1):
        raw = _ask_llm(provider, instructions=instructions, context=prompt_context, attempt=attempt)
        if raw is None:
            continue
        parsed = _parse_llm_json(raw)
        if parsed is None:
            continue
        body_text = parsed.get("body")
        if not isinstance(body_text, str) or not body_text.strip():
            continue
        report = validate_per_claim_cites(body_text)
        if not report.ok:
            _log.info(
                "synthesizer: missing cite paragraphs on attempt %s: %s",
                attempt,
                report.missing_cite_paragraphs,
            )
            continue
        unverified = await verify_citations_exist(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            citations=report.citations,
        )
        if unverified:
            _log.info("synthesizer: unverified citations on attempt %s: %s", attempt, unverified)
            continue
        event_ids = sorted({c.id for c in report.citations if c.kind == "event"})
        return body_text.strip(), report.citations, list(event_ids)
    return None


def _ask_llm(provider: Any, *, instructions: str, context: str, attempt: int) -> str | None:
    suffix = (
        ""
        if attempt == 0
        else (
            "\n\nYour previous reply was rejected — make sure every paragraph contains "
            "at least one [event:UUID] tag drawn from the supplied event ids."
        )
    )
    messages = [
        {
            "role": "system",
            "content": (
                "You are Agent Kenny, the deployment knowledge librarian. "
                "Reply with strict JSON only. Cite every paragraph."
            ),
        },
        {
            "role": "user",
            "content": f"{instructions}{suffix}\n\nContext:\n{context}",
        },
    ]
    try:
        raw = provider.chat_complete(
            messages,
            temperature=_LLM_TEMPERATURE,
            max_output_tokens=_LLM_MAX_OUTPUT_TOKENS,
        )
    except Exception as exc:  # broad: never crash the worker on provider issues
        _log.warning("synthesizer: LLM call failed: %s", exc)
        return None
    text = (raw or "").strip()
    return text or None


def _parse_llm_json(raw: str) -> dict[str, Any] | None:
    text = raw.strip()
    if text.startswith("```"):
        # Strip code fences ``` or ```json
        text = text.split("\n", 1)[-1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return value


async def _require_matrix_node(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_id: uuid.UUID,
) -> MatrixNode | None:
    r = await session.execute(
        select(MatrixNode).where(
            MatrixNode.id == node_id,
            MatrixNode.tenant_id == tenant_id,
            MatrixNode.engagement_id == engagement_id,
        )
    )
    return r.scalar_one_or_none()


async def _require_matrix_insight(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    insight_id: uuid.UUID,
) -> MatrixInsight | None:
    r = await session.execute(
        select(MatrixInsight).where(
            MatrixInsight.id == insight_id,
            MatrixInsight.tenant_id == tenant_id,
            MatrixInsight.engagement_id == engagement_id,
        )
    )
    return r.scalar_one_or_none()


async def _find_anchor_event(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    target_kind: str,
    target_id: uuid.UUID,
    source_kind: str | None,
    preferred_event_id: uuid.UUID | None,
) -> LedgerEvent | None:
    if preferred_event_id is not None:
        r = await session.execute(
            select(LedgerEvent).where(
                LedgerEvent.id == preferred_event_id,
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.engagement_id == engagement_id,
            )
        )
        ev = r.scalar_one_or_none()
        if ev is not None:
            return ev
    from control_plane.domain.ledger import LedgerEventAffects

    stmt = (
        select(LedgerEvent)
        .join(LedgerEventAffects, LedgerEventAffects.event_id == LedgerEvent.id)
        .where(
            LedgerEventAffects.entity_kind == target_kind,
            LedgerEventAffects.entity_id == target_id,
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.engagement_id == engagement_id,
        )
    )
    if source_kind is not None:
        stmt = stmt.where(LedgerEvent.source_kind == source_kind)
    stmt = stmt.order_by(LedgerEvent.occurred_at.desc()).limit(1)
    r = await session.execute(stmt)
    return r.scalar_one_or_none()


async def _walk_causal_chain(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    root_event_id: uuid.UUID,
) -> list[LedgerEvent]:
    """Walk upstream causes from ``root_event_id``, bounded by depth + size."""
    visited: set[uuid.UUID] = {root_event_id}
    frontier: deque[tuple[uuid.UUID, int]] = deque([(root_event_id, 0)])
    collected: list[LedgerEvent] = []
    while frontier and len(collected) < _CHAIN_MAX_NODES:
        current_id, depth = frontier.popleft()
        if depth >= _CHAIN_MAX_DEPTH:
            continue
        parent_ids = list(
            (
                await session.execute(
                    select(LedgerEventCause.caused_by_id).where(LedgerEventCause.event_id == current_id)
                )
            )
            .scalars()
            .all()
        )
        if not parent_ids:
            continue
        parents = list(
            (
                await session.execute(
                    select(LedgerEvent).where(
                        LedgerEvent.id.in_(parent_ids),
                        LedgerEvent.tenant_id == tenant_id,
                        LedgerEvent.engagement_id == engagement_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for parent in parents:
            if parent.id in visited:
                continue
            visited.add(parent.id)
            collected.append(parent)
            frontier.append((parent.id, depth + 1))
            if len(collected) >= _CHAIN_MAX_NODES:
                break
    return collected


def _format_chain_context(
    *,
    title: str,
    anchor: LedgerEvent,
    chain: list[LedgerEvent],
    extra: str | None = None,
) -> str:
    rows = [f"- [event:{anchor.id}] {anchor.occurred_at.isoformat()} | {anchor.source_kind} | {anchor.summary[:200]}"]
    for ev in chain:
        rows.append(f"- [event:{ev.id}] {ev.occurred_at.isoformat()} | {ev.source_kind} | {ev.summary[:200]}")
    block = f"{title}\nAnchor + upstream causes:\n" + "\n".join(rows)
    if extra:
        block += f"\n\nAdditional context:\n{extra[:1000]}"
    return block


def _node_attributes_summary(node: MatrixNode) -> str:
    attrs = node.attributes or {}
    keys = sorted(attrs.keys())
    if not keys:
        return ""
    bullets = []
    for key in keys[:20]:
        value = attrs[key]
        if isinstance(value, str | int | float | bool) or value is None:
            bullets.append(f"- {key}: {value}")
    return "\n".join(bullets)


def _derive_title(*, anchor: LedgerEvent, kind: str) -> str:
    label = {
        "decision_provenance": "Decision provenance",
        "risk_explainer": "Risk explainer",
        "stakeholder_brief": "Stakeholder brief",
    }.get(kind, kind)
    return f"{label}: {anchor.summary[:150]}"[:200]


async def _emit_failure(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    now: datetime,
    kind: str,
    target_id: uuid.UUID,
    anchor_id: uuid.UUID | None,
    reason: str,
    validation: bool = False,
) -> None:
    source_kind = "synthesis_validation_failed" if validation else "synthesis_failed"
    detail: dict[str, Any] = {
        "kind": kind,
        "target_id": str(target_id),
        "reason": reason,
    }
    affects: list[tuple[str, uuid.UUID]] = []
    caused: list[uuid.UUID] = []
    if anchor_id is not None:
        caused.append(anchor_id)
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=now,
        actor_kind="agent:kenny",
        actor_id="synthesizer",
        source_kind=source_kind,
        source_ref=target_id,
        summary=f"synthesis {kind} failed: {reason}"[:500],
        detail=detail,
        caused_by=caused,
        affects=affects,
    )


__all__ = [
    "mark_stale_for_deleted_sources",
    "refresh_decision_provenance",
    "refresh_risk_explainer",
    "refresh_stakeholder_brief",
]
