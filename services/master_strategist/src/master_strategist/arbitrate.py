"""Internal-only Master Strategist arbitration (FR26, Story 6-6). No user UI in V1 (DP10).

Composite score (documented, deterministic):

    strategist_score = 0.45 * confidence + 0.35 * phase_fit + 0.20 * override_strength

where ``override_strength = min(1.0, user_override_count / max_override_scale)`` with
``max_override_scale`` defaulting to 3 (tune at call site).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Literal

ProposalSource = Literal["cartographer", "oracle"]


@dataclass(frozen=True, slots=True)
class StrategistArbitrationConfig:
    """Thresholds on the composite ``strategist_score`` in ``[0, 1]``."""

    queue_threshold: float = 0.55
    """Strictly above this value routes to the Action Queue."""
    low_threshold: float = 0.30
    """At or above this value (and not above ``queue_threshold``) routes to Validation."""
    max_override_scale: float = 3.0
    """Denominator for mapping raw override counts to ``[0, 1]``."""

    def __post_init__(self) -> None:
        if not 0.0 <= self.low_threshold <= self.queue_threshold <= 1.0:
            msg = "require 0 <= low_threshold <= queue_threshold <= 1"
            raise ValueError(msg)
        if self.max_override_scale <= 0:
            msg = "max_override_scale must be positive"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class IncomingProposal:
    """Source agent item (Cartographer or Oracle) before arbitration."""

    proposal_id: uuid.UUID
    source: ProposalSource
    confidence: float
    """Per-proposal confidence in ``[0, 1]`` (caller-normalized)."""
    phase_fit: float
    """How well the proposal matches the tenant phase, ``[0, 1]``."""
    user_override_count: int = 0
    """Count of prior user overrides relevant to this suggestion (non-negative)."""
    payload: dict[str, Any] = field(default_factory=dict)
    """Opaque carry-through for downstream queues (e.g. citation handles)."""


@dataclass(frozen=True, slots=True)
class RankedProposal:
    proposal: IncomingProposal
    strategist_score: float
    rank: int
    """1-based order within its destination queue (lower is higher priority)."""


@dataclass(frozen=True, slots=True)
class SuppressedProposal:
    proposal: IncomingProposal
    strategist_score: float
    reason: str


@dataclass(frozen=True, slots=True)
class AuditSuppressionEvent:
    """Structured audit record for suppressed items (FR26)."""

    proposal_id: uuid.UUID
    source: ProposalSource
    strategist_score: float
    reason: str


@dataclass(frozen=True, slots=True)
class ArbitrationResult:
    action_queue: tuple[RankedProposal, ...]
    user_validation_queue: tuple[RankedProposal, ...]
    suppressed: tuple[SuppressedProposal, ...]
    audit_suppressions: tuple[AuditSuppressionEvent, ...]


def strategist_score(p: IncomingProposal, cfg: StrategistArbitrationConfig) -> float:
    oc = max(0, p.user_override_count)
    override_strength = min(1.0, float(oc) / cfg.max_override_scale)
    raw = 0.45 * p.confidence + 0.35 * p.phase_fit + 0.20 * override_strength
    return max(0.0, min(1.0, float(raw)))


def arbitrate_proposals(
    proposals: tuple[IncomingProposal, ...] | list[IncomingProposal],
    cfg: StrategistArbitrationConfig | None = None,
) -> ArbitrationResult:
    """Route proposals to Action Queue, User Validation Queue, or suppress with audit rows."""
    c = cfg or StrategistArbitrationConfig()
    scored: list[tuple[IncomingProposal, float]] = [(p, strategist_score(p, c)) for p in list(proposals)]
    scored.sort(key=lambda t: t[1], reverse=True)

    action: list[RankedProposal] = []
    validation: list[RankedProposal] = []
    suppressed: list[SuppressedProposal] = []
    audits: list[AuditSuppressionEvent] = []

    for p, s in scored:
        if s > c.queue_threshold:
            action.append(RankedProposal(proposal=p, strategist_score=s, rank=len(action) + 1))
        elif s >= c.low_threshold:
            validation.append(
                RankedProposal(proposal=p, strategist_score=s, rank=len(validation) + 1),
            )
        else:
            reason = f"strategist_score {s:.4f} < low_threshold {c.low_threshold}"
            suppressed.append(SuppressedProposal(proposal=p, strategist_score=s, reason=reason))
            audits.append(
                AuditSuppressionEvent(
                    proposal_id=p.proposal_id,
                    source=p.source,
                    strategist_score=s,
                    reason=reason,
                ),
            )

    return ArbitrationResult(
        action_queue=tuple(action),
        user_validation_queue=tuple(validation),
        suppressed=tuple(suppressed),
        audit_suppressions=tuple(audits),
    )
