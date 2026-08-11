"""E4 — confidence-thresholded auto-accept policy for matrix proposals.

Pure decision logic, kept free of DB and HTTP concerns so the threshold
boundary and the sampling determinism are unit-testable. The route layer
(``engagements_internal.extract_engagement_proposals``) applies the
decision: ``accept`` runs the normal accept path with the distinct
``proposal_auto_accepted`` ledger kind; ``audit`` leaves the proposal
queued with ``payload.sampling_audit = true`` so a human spot-checks it;
``queue`` is the default review-everything behavior.

Sampling is a deterministic hash of the proposal id — not ``random()`` —
so a replayed ingest makes identical decisions and the audit sample is
reproducible from the data alone.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import Any, Literal

AutoAcceptAction = Literal["queue", "audit", "accept"]

# gen_random_uuid() ids are uniformly distributed, so the first 8 hex chars
# of SHA-256(id) map uniformly onto [0, 1).
_BUCKET_DENOMINATOR = float(0xFFFFFFFF)


@dataclass(frozen=True)
class AutoAcceptSettings:
    """Per-tenant policy knobs (columns on ``tenant_llm_configs``).

    ``threshold`` is None when auto-accept is off. Both values are 0..1.
    """

    threshold: float | None
    sampling_audit_rate: float = 0.0

    @property
    def enabled(self) -> bool:
        return self.threshold is not None


@dataclass(frozen=True)
class AutoAcceptDecision:
    action: AutoAcceptAction
    confidence: float | None
    threshold: float | None
    sampled_for_audit: bool


def extract_confidence(payload: dict[str, Any] | None) -> float | None:
    """Read a numeric ``confidence`` from a proposal payload, or None.

    Non-numeric or out-of-range values are treated as absent — a malformed
    confidence must never auto-accept.
    """
    if not isinstance(payload, dict):
        return None
    raw = payload.get("confidence")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    value = float(raw)
    if not (0.0 <= value <= 1.0):
        return None
    return value


def sampling_bucket(proposal_id: uuid.UUID) -> float:
    """Deterministic uniform value in [0, 1) derived from the proposal id."""
    digest = hashlib.sha256(str(proposal_id).encode("ascii")).hexdigest()
    return int(digest[:8], 16) / (_BUCKET_DENOMINATOR + 1.0)


def decide_auto_accept(
    proposal_id: uuid.UUID,
    payload: dict[str, Any] | None,
    settings: AutoAcceptSettings,
) -> AutoAcceptDecision:
    """Decide what happens to one freshly created proposal.

    - policy off, missing/low confidence → ``queue`` (human reviews).
    - confidence >= threshold → ``accept``, except the deterministic
      ``sampling_audit_rate`` fraction which land in ``audit``.
    """
    confidence = extract_confidence(payload)
    if settings.threshold is None or confidence is None or confidence < settings.threshold:
        return AutoAcceptDecision(
            action="queue",
            confidence=confidence,
            threshold=settings.threshold,
            sampled_for_audit=False,
        )
    if sampling_bucket(proposal_id) < settings.sampling_audit_rate:
        return AutoAcceptDecision(
            action="audit",
            confidence=confidence,
            threshold=settings.threshold,
            sampled_for_audit=True,
        )
    return AutoAcceptDecision(
        action="accept",
        confidence=confidence,
        threshold=settings.threshold,
        sampled_for_audit=False,
    )


__all__ = [
    "AutoAcceptAction",
    "AutoAcceptDecision",
    "AutoAcceptSettings",
    "decide_auto_accept",
    "extract_confidence",
    "sampling_bucket",
]
