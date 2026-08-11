"""NFR12: exponential visibility / retry schedule for ingestion (72h window, DLQ via redrive policy)."""

from __future__ import annotations

# Base delay (seconds) after a transient 5xx / network failure before the next receive attempt.
NFR12_BACKOFF_BASE_SEC = 2
# Max delay cap per attempt (5 minutes, NFR12).
NFR12_BACKOFF_MAX_SEC = 300
# SQS (and similar) max retention: 72 hours.
NFR12_MAX_AGE_SEC = 72 * 60 * 60

# Operator guidance (formerly `nfr12_dead_letter_after_receive_hint`, deleted — no callers):
# use an SQS redrive policy so messages older than 72h or repeatedly failing land in a DLQ;
# tune maxReceiveCount from your mean backoff and provider SLAs (Story 3-6). Do not hardcode
# a fixed receive count here — it belongs in the queue policy.


def nfr12_visibility_timeout_seconds(attempt: int) -> int:
    """Exponential schedule: 2s, 4s, 8s… capped at 300s (NFR12). *attempt* starts at 0 after first failure."""
    a = max(0, int(attempt))
    sec = NFR12_BACKOFF_BASE_SEC * (2.0 ** min(8, a))
    return int(min(NFR12_BACKOFF_MAX_SEC, max(1.0, sec)))
