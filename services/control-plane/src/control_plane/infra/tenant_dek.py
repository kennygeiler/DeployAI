"""Per-tenant DEK wrap (AR4) — stub or AWS KMS envelope (future)."""

from __future__ import annotations

import base64
import os

from control_plane.config.settings import get_settings


def wrap_tenant_dek() -> tuple[str, str]:
    """Generate a DEK and return ``(ciphertext_b64, key_id)`` for storage on ``app_tenants``.

    Production path will call KMS; local/tests use a deterministic-size random blob
    and a well-known key id.
    """
    s = get_settings()
    if s.tenant_dek_mode == "aws_kms":
        raise NotImplementedError("AWS KMS DEK wrap — TODO: wire boto3 + CMK from settings (Story 2-5+)")
    raw = os.urandom(32)
    return base64.b64encode(raw).decode("ascii"), "stub-local"
