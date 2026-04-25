"""Deployment phase labels; must match ``control_plane.phases.machine`` (Epic 5)."""

from __future__ import annotations

# Canonical 7-step chain (order matters for ``can_transition``).
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
