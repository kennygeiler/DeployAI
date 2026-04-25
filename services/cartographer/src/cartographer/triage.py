"""Mission-relevance triage (Epic 6, Story 6.1, FR15) — no LLM; deterministic score ∈ [0, 1]."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

from cartographer.metrics import observe_triage

Outcome = Literal["passed", "triaged_out"]


@dataclass(frozen=True, slots=True)
class TriageContext:
    """Tenant mission context: phase + declared objectives (not user per-event)."""

    phase: str
    declared_objectives: tuple[str, ...] = ()
    relevance_threshold: float = 0.3

    def __post_init__(self) -> None:
        if not 0.0 <= self.relevance_threshold <= 1.0:
            msg = "relevance_threshold must be in [0, 1]"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class EventSignals:
    """Per-event features derived from a canonical memory event (Epic 3)."""

    event_id: uuid.UUID
    event_participants: tuple[str, ...] = ()
    event_keywords: tuple[str, ...] = ()
    text_blob: str = ""

    @classmethod
    def from_event_dict(cls, raw: dict[str, Any]) -> EventSignals:
        """Best-effort mapping from a canonical event document."""
        eid = raw.get("id")
        euuid = eid if isinstance(eid, uuid.UUID) else uuid.UUID(str(eid)) if eid else uuid.uuid4()
        parts = raw.get("participants") or raw.get("event_participants") or []
        if not isinstance(parts, (list, tuple)):
            parts = []
        pnorm = tuple(str(p).strip() for p in parts if str(p).strip())
        kws = raw.get("event_keywords") or raw.get("keywords") or []
        if not isinstance(kws, (list, tuple)):
            kws = []
        kwnorm = tuple(str(k).strip().lower() for k in kws if str(k).strip())
        subj = str(raw.get("subject") or raw.get("title") or "")
        body = str(raw.get("body") or raw.get("text") or raw.get("content") or raw.get("snippet") or "")
        blob = f"{subj} {body}".strip()
        return cls(event_id=euuid, event_participants=pnorm, event_keywords=kwnorm, text_blob=blob)


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^a-z0-9]+", text.lower()) if len(t) >= 3}


@dataclass(frozen=True, slots=True)
class TriageResult:
    event_id: uuid.UUID
    relevance_score: float
    outcome: Outcome
    triaged_out: bool
    reason: str
    would_consume_extraction: bool
    # Logged; no LLM for triage
    log_fields: dict[str, Any] = field(default_factory=dict)


def score_relevance(ctx: TriageContext, event: EventSignals) -> float:
    """Heuristic ∈ [0, 1] from phase + objectives vs participants, keywords, text."""
    if not ctx.declared_objectives:
        return 0.0
    obj = _tokens(" ".join(ctx.declared_objectives))
    if not obj:
        return 0.0
    ev: set[str] = set(event.event_keywords)
    ev |= _tokens(event.text_blob)
    for p in event.event_participants:
        ev |= _tokens(p)
    if not ev:
        return 0.0
    inter = len(obj & ev)
    union = len(obj | ev)
    jacc = inter / max(1, union)
    # Substring match for small stem gaps (e.g. schedule / schedules) without an LLM stemmer.
    sub_boost = 0.0
    blob = f"{' '.join(event.event_keywords)} {event.text_blob}".lower()
    for term in obj:
        if len(term) >= 5 and term in blob:
            sub_boost = min(0.25, sub_boost + 0.05)
    # Phase-aware weight: later phases get a small floor boost (still no LLM).
    phase_lo = ctx.phase.lower()
    phase_weight = 1.0
    if "p5" in phase_lo or "execution" in phase_lo or "p6" in phase_lo or "p7" in phase_lo:
        phase_weight = 1.05
    elif "p1" in phase_lo or "pre" in phase_lo or "p2" in phase_lo or "p3" in phase_lo or "p4" in phase_lo:
        phase_weight = 0.95
    part_boost = 0.0
    for p in event.event_participants:
        ptoks = _tokens(p)
        if ptoks & obj:
            part_boost = min(0.2, part_boost + 0.1)
    raw = (jacc * 0.75 + (inter / max(1, len(obj))) * 0.2 + part_boost + sub_boost) * phase_weight
    return max(0.0, min(1.0, float(raw)))


def triage_event(
    ctx: TriageContext,
    event: EventSignals,
    *,
    tenant_id: str = "system",
) -> TriageResult:
    """Decide pass vs triage_out; update Prometheus metrics; does not call any LLM."""
    score = score_relevance(ctx, event)
    triaged_out = score < ctx.relevance_threshold
    outcome: Outcome = "triaged_out" if triaged_out else "passed"
    if triaged_out:
        if not ctx.declared_objectives:
            reason = "no_declared_objectives"
        elif score < 0.01:
            reason = "no_keyword_overlap"
        else:
            reason = "below_relevance_threshold"
    else:
        reason = "relevance_threshold_met"
    tr = TriageResult(
        event_id=event.event_id,
        relevance_score=score,
        outcome=outcome,
        triaged_out=triaged_out,
        reason=reason,
        would_consume_extraction=not triaged_out,
        log_fields={
            "event_id": str(event.event_id),
            "phase": ctx.phase,
            "tenant_id": tenant_id,
            "relevance_score": score,
            "threshold": ctx.relevance_threshold,
            "outcome": outcome,
        },
    )
    observe_triage(
        tenant_id=tenant_id,
        phase=ctx.phase,
        outcome=outcome,
    )
    return tr
