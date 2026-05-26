"""Portfolio scenario SQL builder.

Thin parameterised analog of ``bluestate/builder.py``. Each engagement
gets its own SQL block via ``templates.build_engagement_sql``; the
portfolio builder concatenates the five blocks under one BEGIN/COMMIT
when run via psql.
"""

from __future__ import annotations

from control_plane.scenarios.portfolio.engagements import (
    PORTFOLIO_ENGAGEMENTS,
    PORTFOLIO_TENANT_ID,
    EngagementConfig,
)
from control_plane.scenarios.portfolio.templates import (
    TimeAnchor,
    build_engagement_sql,
)

__all__ = [
    "PORTFOLIO_ENGAGEMENTS",
    "PORTFOLIO_TENANT_ID",
    "EngagementConfig",
    "TimeAnchor",
    "build_engagement_sql",
    "build_portfolio_sql",
]


def build_portfolio_sql(
    anchor: TimeAnchor,
    *,
    tenant_id: str = PORTFOLIO_TENANT_ID,
    actor_email: str = "sarah.chen@deployai.com",
) -> str:
    """Concatenate per-engagement SQL into one psql-runnable block."""
    parts: list[str] = ["BEGIN;"]
    for config in PORTFOLIO_ENGAGEMENTS:
        parts.append(
            build_engagement_sql(
                config,
                tenant_id=tenant_id,
                anchor=anchor,
                actor_email=actor_email,
            )
        )
    parts.append("COMMIT;")
    return "\n".join(parts)
