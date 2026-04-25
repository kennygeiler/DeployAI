"""State machine rules for ``tenant_deployment_phases``."""

from __future__ import annotations

# Canonical labels (PRD / Epic 5 AC)
DEPLOYMENT_PHASES: tuple[str, ...] = (
    "P1_pre_engagement",
    "P2_discovery",
    "P3_ecosystem_mapping",
    "P4_design",
    "P5_pilot",
    "P6_scale",
    "P7_inheritance",
)

default_phase = DEPLOYMENT_PHASES[0]


def can_transition(frm: str, to: str) -> bool:
    if frm not in DEPLOYMENT_PHASES or to not in DEPLOYMENT_PHASES:
        return False
    if frm == to:
        return False
    i = DEPLOYMENT_PHASES.index(frm)
    j = DEPLOYMENT_PHASES.index(to)
    return j == i + 1
