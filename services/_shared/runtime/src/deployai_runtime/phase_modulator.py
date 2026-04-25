"""Phase-aware weights for retrieval and alert thresholds (Epic 5, Story 5.6, FR32)."""

from __future__ import annotations

from typing import Literal

DeploymentPhase = Literal[
    "P1_pre_engagement",
    "P2_discovery",
    "P3_ecosystem_mapping",
    "P4_design",
    "P5_pilot",
    "P6_scale",
    "P7_inheritance",
]

# Per-phase multipliers applied to each candidate's base score (0–1)
_WEIGHTS: dict[DeploymentPhase, float] = {
    "P1_pre_engagement": 0.9,
    "P2_discovery": 1.1,
    "P3_ecosystem_mapping": 1.0,
    "P4_design": 1.0,
    "P5_pilot": 1.15,
    "P6_scale": 1.2,
    "P7_inheritance": 0.95,
}

# Minimum confidence to surface an in-meeting alert
_ALERT_FLOOR: dict[DeploymentPhase, float] = {
    "P1_pre_engagement": 0.45,
    "P2_discovery": 0.4,
    "P3_ecosystem_mapping": 0.5,
    "P4_design": 0.55,
    "P5_pilot": 0.65,
    "P6_scale": 0.7,
    "P7_inheritance": 0.6,
}


def apply_phase_weights(phase: DeploymentPhase, scores: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Re-rank (key, base_score) with a phase weight; return sorted by adjusted score desc."""
    w = _WEIGHTS.get(phase, 1.0)
    adj = [(k, min(1.0, s * w)) for k, s in scores]
    adj.sort(key=lambda x: x[1], reverse=True)
    return adj


def alert_confidence_floor(phase: DeploymentPhase) -> float:
    return _ALERT_FLOOR[phase]
