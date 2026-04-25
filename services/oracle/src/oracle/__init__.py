"""DeployAI Oracle — phase-gated retrieval and confidence surfacing (Epic 6)."""

from oracle.budget import (
    PRIMARY_BUDGET,
    BudgetedOracleResponse,
    OracleSurface,
    RankedOutItem,
    apply_three_item_budget,
    assert_primary_at_most_three,
)
from oracle.retrieve import (
    CorpusConfidenceMarker,
    ExplicitNullResult,
    OracleItem,
    OracleResponse,
    OracleRetrievalRequest,
    oracle_retrieve,
)

__all__ = [
    "PRIMARY_BUDGET",
    "BudgetedOracleResponse",
    "CorpusConfidenceMarker",
    "ExplicitNullResult",
    "OracleItem",
    "OracleResponse",
    "OracleRetrievalRequest",
    "OracleSurface",
    "RankedOutItem",
    "apply_three_item_budget",
    "assert_primary_at_most_three",
    "oracle_retrieve",
]
