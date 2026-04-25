"""Master Strategist — internal arbitration, phase proposals, degradation (Epic 6)."""

from master_strategist.arbitrate import (
    ArbitrationResult,
    AuditSuppressionEvent,
    IncomingProposal,
    RankedProposal,
    StrategistArbitrationConfig,
    SuppressedProposal,
    arbitrate_proposals,
    strategist_score,
)
from master_strategist.degradation import AgentErrorState, agent_error_to_canonical_payload
from master_strategist.metrics import AGENT_FAILURES, record_agent_failure
from master_strategist.phase_propose import (
    PhaseTransitionProposalBundle,
    build_control_plane_propose_body,
    build_phase_transition_bundle,
    should_propose_phase_transition,
)
from master_strategist.phases import DEPLOYMENT_PHASES, can_transition, default_phase

__all__ = [
    "AGENT_FAILURES",
    "DEPLOYMENT_PHASES",
    "AgentErrorState",
    "ArbitrationResult",
    "AuditSuppressionEvent",
    "IncomingProposal",
    "PhaseTransitionProposalBundle",
    "RankedProposal",
    "StrategistArbitrationConfig",
    "SuppressedProposal",
    "agent_error_to_canonical_payload",
    "arbitrate_proposals",
    "build_control_plane_propose_body",
    "build_phase_transition_bundle",
    "can_transition",
    "default_phase",
    "record_agent_failure",
    "should_propose_phase_transition",
    "strategist_score",
]
