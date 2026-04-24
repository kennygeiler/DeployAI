"""Per-tenant DEK wrap (AR4) — stub or AWS KMS envelope (future)."""

from __future__ import annotations

import base64
import os

from control_plane.config.settings import get_settings


def wrap_tenant_dek() -> tuple[str, str]:
    """Generate a DEK and return ``(stored_b64, key_id)`` for ``app_tenants`` columns.

    With ``tenant_dek_mode=aws_kms``, the stored value should be KMS-wrapped ciphertext.
    The ``stub`` mode stores Base64-encoded raw key material under the same column names
    so the row shape matches production; do not treat stub values as cryptographic proof
    of KMS use.
    """
    s = get_settings()
    if s.tenant_dek_mode == "aws_kms":
        raise NotImplementedError("AWS KMS DEK wrap — TODO: wire boto3 + CMK from settings (Story 2-5+)")
    raw = os.urandom(32)
    return base64.b64encode(raw).decode("ascii"), "stub-local"
