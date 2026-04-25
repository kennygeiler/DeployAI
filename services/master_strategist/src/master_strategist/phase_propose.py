"""Phase-transition proposal DTOs aligned with control-plane internal API (FR31, Story 6-7).

The control plane accepts ``POST /internal/v1/tenants/{tid}/phase-transitions/propose`` with
``from_phase``, ``to_phase``, ``evidence_event_ids``, ``proposer_agent``, ``reason``.

This module builds that body plus keeps **citation envelopes** for evidence (story AC) alongside
the UUID list the API stores.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from deployai_citation.citation import CitationEnvelopeV01

from master_strategist.phases import DEPLOYMENT_PHASES, can_transition, default_phase


@dataclass(frozen=True, slots=True)
class PhaseTransitionProposalBundle:
    """Strategist-side package for a phase shift (internal / headless — DP10)."""

    tenant_id: uuid.UUID
    from_phase: str
    to_phase: str
    evidence_event_ids: tuple[uuid.UUID, ...]
    evidence_citations: tuple[CitationEnvelopeV01, ...]
    proposer_agent: str
    reason: str
    category: str = "phase_transition"


def build_control_plane_propose_body(bundle: PhaseTransitionProposalBundle) -> dict[str, object]:
    """JSON-serializable body for ``ProposeBody`` (control plane)."""
    return {
        "from_phase": bundle.from_phase,
        "to_phase": bundle.to_phase,
        "evidence_event_ids": [str(x) for x in bundle.evidence_event_ids],
        "proposer_agent": bundle.proposer_agent,
        "reason": bundle.reason,
    }


def should_propose_phase_transition(
    *,
    evidence_count: int,
    avg_confidence: float,
    min_evidence: int = 2,
    min_avg_confidence: float = 0.55,
) -> bool:
    """Cheap readiness heuristic (deterministic; product can replace with richer logic)."""
    return evidence_count >= min_evidence and avg_confidence >= min_avg_confidence


def build_phase_transition_bundle(
    *,
    tenant_id: uuid.UUID,
    current_phase: str,
    target_phase: str,
    evidence_events: tuple[uuid.UUID, ...],
    evidence_citations: tuple[CitationEnvelopeV01, ...],
    proposer_agent: str,
    reason: str,
) -> PhaseTransitionProposalBundle | None:
    """Return a bundle only if ``can_transition`` allows the single-step hop."""
    if current_phase not in DEPLOYMENT_PHASES:
        current_phase = default_phase
    if not can_transition(current_phase, target_phase):
        return None
    if len(evidence_events) != len(evidence_citations):
        msg = "evidence_events and evidence_citations must align 1:1"
        raise ValueError(msg)
    return PhaseTransitionProposalBundle(
        tenant_id=tenant_id,
        from_phase=current_phase,
        to_phase=target_phase,
        evidence_event_ids=evidence_events,
        evidence_citations=evidence_citations,
        proposer_agent=proposer_agent,
        reason=reason,
    )
