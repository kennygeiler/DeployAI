"""DeployAI Oracle — phase-gated retrieval and confidence surfacing (Epic 6)."""

from oracle.retrieve import (
    CorpusConfidenceMarker,
    ExplicitNullResult,
    OracleItem,
    OracleResponse,
    OracleRetrievalRequest,
    oracle_retrieve,
)

__all__ = [
    "CorpusConfidenceMarker",
    "ExplicitNullResult",
    "OracleItem",
    "OracleResponse",
    "OracleRetrievalRequest",
    "oracle_retrieve",
]
