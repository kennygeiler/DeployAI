"""Voyage-3 embedding client + helpers (v2 Phase 5.5 Wave B, scope-v2 §10.2).

Embeddings are the **fallback** path for fuzzy recall (see ``docs/agent-kenny/
ethos.md``). The curated synthesis substrate stays the hot path; this module
exists to power ``vector_search`` for moderate-similarity questions the index
can't answer.
"""

from control_plane.agents.agent_kenny.embeddings.voyage_client import (
    VOYAGE_DIM,
    VOYAGE_MODEL,
    VoyageEmbedder,
)

__all__ = ["VOYAGE_DIM", "VOYAGE_MODEL", "VoyageEmbedder"]
