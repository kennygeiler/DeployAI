"""7-phase deployment framework (Epic 5, Story 5.4)."""

from control_plane.phases.machine import (
    DEPLOYMENT_PHASES,
    can_transition,
    default_phase,
)

__all__ = [
    "DEPLOYMENT_PHASES",
    "can_transition",
    "default_phase",
]
