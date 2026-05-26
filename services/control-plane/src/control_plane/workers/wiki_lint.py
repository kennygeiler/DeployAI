"""Substrate-integrity lint worker (v2 Phase 0.6, scope-v2 §4).

Background scanner that flags integrity issues on the curated synthesis
substrate. **Flags-only — does NOT mutate content.** Strategists +
Kenny resolve flagged issues out-of-band by setting ``resolved_at``.

Five check functions run against a single tenant + engagement scope:

- ``check_contradictions`` — v0 heuristic: two kenny insights produced
  within 14 days that share a citation_node_id, where one body contains
  approval phrasing and the other rejection phrasing. LLM-assisted v1
  is a follow-up TODO.
- ``check_stale`` — kenny/oracle insights with ``last_refreshed_at`` older
  than 30 days whose source events have causal descendants newer than the
  insight's refresh timestamp. Mutates ``stale=true`` on the insight row
  AND emits a lint flag.
- ``check_orphans`` — insights whose ``citation_event_ids`` reference
  events that no longer exist in this tenant + engagement.
- ``check_missing_cite`` — matrix_nodes whose ``attributes.description``
  has a paragraph (blank-line separated) with zero ``[event:…]`` /
  ``[node:…]`` / ``[insight:…]`` cites. Reuses
  ``claim_cite.validate_per_claim_cites``.
- ``check_broken_cite`` — every citation token parsed out of
  matrix_nodes.attributes.description AND matrix_insights.body whose
  UUID does not resolve to a row in this tenant + engagement. Reuses
  ``claim_cite.verify_citations_exist``.

Each check function returns a list of ``LintFinding`` (tuple-shaped) the
caller upserts into ``lint_flags``. ``run_lint`` is the orchestrator the
admin route + ledger emitter both call.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.synthesis.claim_cite import (
    CITATION_RE,
    Citation,
    validate_per_claim_cites,
    verify_citations_exist,
)
from control_plane.domain.canonical_memory.matrix import (
    MatrixInsight,
    MatrixNode,
)
from control_plane.domain.ledger import LedgerEvent, LedgerEventCause
from control_plane.domain.lint import LintFlag

_log = logging.getLogger(__name__)

_STALE_THRESHOLD_DAYS = 30
_CONTRADICTION_WINDOW_DAYS = 14

# v0 heuristic vocabularies — case-insensitive substring match. LLM-assisted
# v1 will replace this with a structured-output disagree/agree probe.
_APPROVAL_TOKENS: tuple[str, ...] = (
    "approved",
    "approve",
    "accepted",
    "ratified",
    "ratify",
    "green-lit",
    "greenlit",
    "go-ahead",
    "signed off",
    "sign-off",
)
_REJECTION_TOKENS: tuple[str, ...] = (
    "rejected",
    "reject",
    "denied",
    "deny",
    "blocked",
    "vetoed",
    "veto",
    "abandoned",
    "killed",
    "withdrawn",
)


LintFinding = tuple[str, str, uuid.UUID, dict[str, Any]]
"""``(kind, target_kind, target_id, detail)`` tuple emitted by every check."""


@dataclass(frozen=True)
class LintRunSummary:
    flag_count: int
    by_kind: dict[str, int]


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


async def run_lint(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    now: datetime,
) -> LintRunSummary:
    """Run all 5 checks; UPSERT findings into ``lint_flags``.

    De-duplication: an open flag with the same ``(kind, target_kind,
    target_id, _detail_fingerprint(detail))`` is left alone — we don't
    pile up duplicates per run. Resolved flags do not block new flags
    with the same fingerprint (so a re-broken citation re-flags).
    """
    findings: list[LintFinding] = []
    findings.extend(await check_contradictions(session, tenant_id=tenant_id, engagement_id=engagement_id))
    findings.extend(await check_stale(session, tenant_id=tenant_id, engagement_id=engagement_id, now=now))
    findings.extend(await check_orphans(session, tenant_id=tenant_id, engagement_id=engagement_id))
    findings.extend(await check_missing_cite(session, tenant_id=tenant_id, engagement_id=engagement_id))
    findings.extend(await check_broken_cite(session, tenant_id=tenant_id, engagement_id=engagement_id))

    by_kind: dict[str, int] = {}
    new_count = 0
    for kind, target_kind, target_id, detail in findings:
        inserted = await _upsert_flag(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            kind=kind,
            target_kind=target_kind,
            target_id=target_id,
            detail=detail,
            now=now,
        )
        if inserted:
            new_count += 1
            by_kind[kind] = by_kind.get(kind, 0) + 1
    if new_count:
        await session.flush()
    return LintRunSummary(flag_count=new_count, by_kind=by_kind)


# ---------------------------------------------------------------------------
# Check functions
# ---------------------------------------------------------------------------


async def check_contradictions(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> list[LintFinding]:
    """v0 heuristic: pair kenny insights inside a 14-day window that share a
    cited decision node and where one body reads as approval, the other as
    rejection. LLM-assisted v1 is a follow-up TODO once the eval harness in
    Phase 6 can score false-positive rate.
    """
    stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tenant_id,
        MatrixInsight.engagement_id == engagement_id,
        MatrixInsight.agent == "kenny",
    )
    rows = list((await session.execute(stmt)).scalars().all())
    findings: list[LintFinding] = []
    window = timedelta(days=_CONTRADICTION_WINDOW_DAYS)
    for i in range(len(rows)):
        a = rows[i]
        a_nodes = set(a.citation_node_ids or ())
        a_events = set(a.citation_event_ids or ())
        if not (a_nodes or a_events):
            continue
        a_stance = _stance(a.body)
        if a_stance is None:
            continue
        for j in range(i + 1, len(rows)):
            b = rows[j]
            b_nodes = set(b.citation_node_ids or ())
            b_events = set(b.citation_event_ids or ())
            overlap_nodes = a_nodes & b_nodes
            overlap_events = a_events & b_events
            if not (overlap_nodes or overlap_events):
                continue
            delta = abs((a.created_at - b.created_at).total_seconds())
            if delta > window.total_seconds():
                continue
            b_stance = _stance(b.body)
            if b_stance is None or b_stance == a_stance:
                continue
            shared_node = next(iter(overlap_nodes), None)
            detail: dict[str, Any] = {
                "heuristic": "v0_approval_vs_rejection",
                "other_insight_id": str(b.id),
                "a_stance": a_stance,
                "b_stance": b_stance,
                "overlap_node_ids": [str(n) for n in sorted(overlap_nodes)],
                "overlap_event_ids": [str(e) for e in sorted(overlap_events)],
            }
            if shared_node is not None:
                detail["decision_node_id"] = str(shared_node)
            findings.append(("contradiction", "matrix_insight", a.id, detail))
    return findings


async def check_stale(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    now: datetime,
) -> list[LintFinding]:
    """Flag synthesis whose source events have downstream successors arriving
    after the insight's last refresh, AND whose refresh is older than 30 days.
    """
    cutoff = now - timedelta(days=_STALE_THRESHOLD_DAYS)
    stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tenant_id,
        MatrixInsight.engagement_id == engagement_id,
        MatrixInsight.agent.in_(("kenny", "oracle")),
        MatrixInsight.last_refreshed_at < cutoff,
    )
    rows = list((await session.execute(stmt)).scalars().all())
    findings: list[LintFinding] = []
    for row in rows:
        sources = list(row.citation_event_ids or ())
        if not sources:
            continue
        descendants_stmt = (
            select(LedgerEvent.id, LedgerEvent.occurred_at, LedgerEventCause.caused_by_id)
            .join(LedgerEventCause, LedgerEventCause.event_id == LedgerEvent.id)
            .where(
                LedgerEventCause.caused_by_id.in_(sources),
                LedgerEvent.tenant_id == tenant_id,
                LedgerEvent.engagement_id == engagement_id,
                LedgerEvent.occurred_at > row.last_refreshed_at,
            )
        )
        descendants = list((await session.execute(descendants_stmt)).all())
        if not descendants:
            continue
        # Mutate the insight row's stale flag — scope-v2 §4 explicitly allows
        # this single mutation; everything else stays flag-only.
        if not row.stale:
            row.stale = True
        descendant_ids = [str(d[0]) for d in descendants]
        detail: dict[str, Any] = {
            "last_refreshed_at": row.last_refreshed_at.isoformat(),
            "newer_descendant_event_ids": descendant_ids[:20],
            "newer_descendant_count": len(descendants),
        }
        findings.append(("stale", "matrix_insight", row.id, detail))
    return findings


async def check_orphans(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> list[LintFinding]:
    """Flag insights whose ``citation_event_ids`` references missing events."""
    stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tenant_id,
        MatrixInsight.engagement_id == engagement_id,
        MatrixInsight.agent.in_(("kenny", "oracle")),
    )
    rows = list((await session.execute(stmt)).scalars().all())
    findings: list[LintFinding] = []
    all_ids: set[uuid.UUID] = set()
    for row in rows:
        all_ids.update(row.citation_event_ids or ())
    if not all_ids:
        return findings
    existing_q = await session.execute(
        select(LedgerEvent.id).where(
            LedgerEvent.id.in_(all_ids),
            LedgerEvent.tenant_id == tenant_id,
            LedgerEvent.engagement_id == engagement_id,
        )
    )
    existing = set(existing_q.scalars().all())
    for row in rows:
        missing = [eid for eid in (row.citation_event_ids or ()) if eid not in existing]
        if not missing:
            continue
        detail: dict[str, Any] = {
            "missing_event_ids": sorted(str(eid) for eid in missing),
            "missing_count": len(missing),
        }
        findings.append(("orphan", "matrix_insight", row.id, detail))
    return findings


async def check_missing_cite(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> list[LintFinding]:
    """Flag matrix_nodes whose attributes.description has a paragraph without
    any inline cite tag. One finding per offending paragraph.
    """
    stmt = select(MatrixNode).where(
        MatrixNode.tenant_id == tenant_id,
        MatrixNode.engagement_id == engagement_id,
    )
    rows = list((await session.execute(stmt)).scalars().all())
    findings: list[LintFinding] = []
    for row in rows:
        attrs = row.attributes or {}
        description = attrs.get("description")
        if not isinstance(description, str) or not description.strip():
            continue
        report = validate_per_claim_cites(description)
        for paragraph_index in report.missing_cite_paragraphs:
            detail: dict[str, Any] = {
                "paragraph_index": paragraph_index,
                "total_paragraphs": report.paragraphs,
            }
            findings.append(("missing_cite", "matrix_node", row.id, detail))
    return findings


async def check_broken_cite(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
) -> list[LintFinding]:
    """Flag every cite token whose UUID does not resolve in this scope.

    Parses tokens from matrix_nodes.attributes.description AND
    matrix_insights.body. One finding per ``(target, unresolved_citation)``
    pair so the dashboard can surface specific bad UUIDs.
    """
    node_stmt = select(MatrixNode).where(
        MatrixNode.tenant_id == tenant_id,
        MatrixNode.engagement_id == engagement_id,
    )
    insight_stmt = select(MatrixInsight).where(
        MatrixInsight.tenant_id == tenant_id,
        MatrixInsight.engagement_id == engagement_id,
    )
    node_rows = list((await session.execute(node_stmt)).scalars().all())
    insight_rows = list((await session.execute(insight_stmt)).scalars().all())

    findings: list[LintFinding] = []
    for node in node_rows:
        attrs = node.attributes or {}
        description = attrs.get("description")
        if not isinstance(description, str) or not description.strip():
            continue
        unresolved = await _unresolved_citations(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            prose=description,
        )
        for cite in unresolved:
            detail: dict[str, Any] = {
                "citation_kind": cite.kind,
                "citation_id": str(cite.id),
                "field": "attributes.description",
            }
            findings.append(("broken_cite", "matrix_node", node.id, detail))

    for insight in insight_rows:
        body = insight.body or ""
        if not body.strip():
            continue
        unresolved = await _unresolved_citations(
            session,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            prose=body,
        )
        for cite in unresolved:
            detail = {
                "citation_kind": cite.kind,
                "citation_id": str(cite.id),
                "field": "body",
            }
            findings.append(("broken_cite", "matrix_insight", insight.id, detail))
    return findings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _stance(body: str | None) -> str | None:
    """Classify a body as ``'approval'`` / ``'rejection'`` / ``None``.

    v0 heuristic: lowercase substring match against curated token lists.
    """
    if not body:
        return None
    lower = body.lower()
    approve = any(token in lower for token in _APPROVAL_TOKENS)
    reject = any(token in lower for token in _REJECTION_TOKENS)
    if approve and not reject:
        return "approval"
    if reject and not approve:
        return "rejection"
    return None


def _parse_citations(text: str) -> list[Citation]:
    """Extract every cite tag in ``text`` as deduped ``Citation`` rows."""
    if not text:
        return []
    seen: set[tuple[str, uuid.UUID]] = set()
    out: list[Citation] = []
    for kind, raw in CITATION_RE.findall(text):
        try:
            cid = uuid.UUID(raw)
        except ValueError:
            continue
        key = (kind, cid)
        if key in seen:
            continue
        seen.add(key)
        out.append(Citation(kind=kind, id=cid))
    return out


async def _unresolved_citations(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    prose: str,
) -> list[Citation]:
    citations = _parse_citations(prose)
    if not citations:
        return []
    return await verify_citations_exist(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        citations=citations,
    )


def _detail_fingerprint(detail: dict[str, Any]) -> str:
    """Stable JSON serialization for de-duping flags with identical detail."""
    return json.dumps(detail, sort_keys=True, default=str)


async def _upsert_flag(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    kind: str,
    target_kind: str,
    target_id: uuid.UUID,
    detail: dict[str, Any],
    now: datetime,
) -> bool:
    """Insert one ``lint_flags`` row if no equivalent open flag exists.

    Returns ``True`` when a row was inserted, ``False`` when skipped as a
    duplicate of an already-open flag.
    """
    existing_stmt = select(LintFlag).where(
        LintFlag.tenant_id == tenant_id,
        LintFlag.engagement_id == engagement_id,
        LintFlag.kind == kind,
        LintFlag.target_kind == target_kind,
        LintFlag.target_id == target_id,
        LintFlag.resolved_at.is_(None),
    )
    rows = list((await session.execute(existing_stmt)).scalars().all())
    fingerprint = _detail_fingerprint(detail)
    for row in rows:
        if _detail_fingerprint(row.detail or {}) == fingerprint:
            return False
    session.add(
        LintFlag(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            kind=kind,
            target_kind=target_kind,
            target_id=target_id,
            detail=detail,
            flagged_at=now,
        )
    )
    return True


__all__ = [
    "LintFinding",
    "LintRunSummary",
    "check_broken_cite",
    "check_contradictions",
    "check_missing_cite",
    "check_orphans",
    "check_stale",
    "run_lint",
]
