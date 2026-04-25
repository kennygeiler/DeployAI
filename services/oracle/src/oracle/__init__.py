"""DeployAI Oracle — phase-gated retrieval and confidence surfacing (Epic 6)."""

from oracle.budget import (
    PRIMARY_BUDGET,
    BudgetedOracleResponse,
    OracleSurface,
    RankedOutItem,
    apply_three_item_budget,
    assert_primary_at_most_three,
)
from oracle.posture import (
    assert_oracle_items_suggestions_only,
    validate_budgeted_oracle_posture,
    validate_oracle_response_posture,
)
from oracle.retrieve import (
    ActionPosture,
    CorpusConfidenceMarker,
    ExplicitNullResult,
    OracleItem,
    OracleResponse,
    OracleRetrievalRequest,
    oracle_retrieve,
)

__all__ = [
    "PRIMARY_BUDGET",
    "ActionPosture",
    "BudgetedOracleResponse",
    "CorpusConfidenceMarker",
    "ExplicitNullResult",
    "OracleItem",
    "OracleResponse",
    "OracleRetrievalRequest",
    "OracleSurface",
    "RankedOutItem",
    "apply_three_item_budget",
    "assert_oracle_items_suggestions_only",
    "assert_primary_at_most_three",
    "oracle_retrieve",
    "validate_budgeted_oracle_posture",
    "validate_oracle_response_posture",
]
