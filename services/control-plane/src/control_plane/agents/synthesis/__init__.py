"""Synthesis agent helpers (v2 Phase 0.5).

Hosts the claim-level citation validator that every synthesized
``matrix_insights`` body must pass before persistence. The synthesizer
workers (``control_plane.workers.synthesizer``) call into this module to
reject hallucinated cites before they reach the curated substrate.
"""

from control_plane.agents.synthesis.claim_cite import (
    CITATION_RE,
    Citation,
    ClaimValidationReport,
    validate_per_claim_cites,
    verify_citations_exist,
)

__all__ = [
    "CITATION_RE",
    "Citation",
    "ClaimValidationReport",
    "validate_per_claim_cites",
    "verify_citations_exist",
]
