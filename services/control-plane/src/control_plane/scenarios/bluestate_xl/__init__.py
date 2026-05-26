"""BlueState Health Long-Cycle 5-Year demo scenario.

10x the volume of the standard BlueState scenario. Used as the workhorse
fixture for Agent Kenny v2 testing and the Phase 6 eval harness.
"""

from __future__ import annotations

from control_plane.scenarios.bluestate_xl.builder import (
    CUSTOMER_ACCOUNT,
    ENGAGEMENT_ID,
    ENGAGEMENT_NAME,
    ENGAGEMENT_PHASE,
    TENANT_ID,
    TENANT_NAME,
    USER_BIZDEV_ID,
    USER_FDE_ID,
    USER_STRATEGIST_ID,
    XlTimeAnchor,
    build_xl_scenario_sql,
)
from control_plane.scenarios.bluestate_xl.runner import (
    XlScenarioSummary,
    apply_bluestate_xl_scenario,
    xl_engagement_exists_for_tenant,
)

__all__ = [
    "CUSTOMER_ACCOUNT",
    "ENGAGEMENT_ID",
    "ENGAGEMENT_NAME",
    "ENGAGEMENT_PHASE",
    "TENANT_ID",
    "TENANT_NAME",
    "USER_BIZDEV_ID",
    "USER_FDE_ID",
    "USER_STRATEGIST_ID",
    "XlScenarioSummary",
    "XlTimeAnchor",
    "apply_bluestate_xl_scenario",
    "build_xl_scenario_sql",
    "xl_engagement_exists_for_tenant",
]
