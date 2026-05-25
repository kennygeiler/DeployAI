"""Timeline ledger writer (Phase F1.b).

Re-exports ``emit_ledger_event`` — the single entry point that every
write site uses to append a row onto the engagement-scoped causal ledger
described in ``docs/design/timeline-ledger.md`` §4.
"""

from __future__ import annotations

from control_plane.ledger.emitter import (
    ALLOWED_SOURCE_KINDS,
    AffectsEntry,
    emit_ledger_event,
)

__all__ = ["ALLOWED_SOURCE_KINDS", "AffectsEntry", "emit_ledger_event"]
