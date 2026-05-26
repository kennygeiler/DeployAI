"""DeployAI Portfolio - 5 sibling engagements x 26 weeks under one tenant.

Stress fixture for cross-engagement isolation. Agent Kenny scoped to one
engagement must never leak data from sibling engagements.
"""

from __future__ import annotations

from control_plane.scenarios.portfolio.engagements import (
    PORTFOLIO_ENGAGEMENT_IDS,
    PORTFOLIO_ENGAGEMENTS,
    PORTFOLIO_TENANT_ID,
    EngagementConfig,
)
from control_plane.scenarios.portfolio.runner import (
    PortfolioSummary,
    apply_portfolio_scenario,
    portfolio_engagements_exist_for_tenant,
)

__all__ = [
    "PORTFOLIO_ENGAGEMENTS",
    "PORTFOLIO_ENGAGEMENT_IDS",
    "PORTFOLIO_TENANT_ID",
    "EngagementConfig",
    "PortfolioSummary",
    "apply_portfolio_scenario",
    "portfolio_engagements_exist_for_tenant",
]
