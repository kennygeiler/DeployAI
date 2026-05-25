"""Intelligence layer — analyzers that derive temporal insights from the ledger.

Per `docs/design/timeline-ledger.md` §5. Each analyzer is pure
(input session+window → output `TemporalInsightWrite`) and idempotent
(deterministic insight IDs so re-runs upsert cleanly).
"""

from __future__ import annotations

from control_plane.intelligence.base import Analyzer, TemporalInsightWrite

__all__ = ["Analyzer", "TemporalInsightWrite"]
