"""AES-GCM sealing for private override annotations (Epic 10.5 — NFR37 stub).

Production should replace tenant wrapping with KMS + per-annotation DEK wrapping
documented in ops runbooks. This module keeps crypto auditable and deterministic
enough for integration tests (tenant-bound wrapping key from SHA-256).
"""

from __future__ import annotations

import hashlib
import os
import uuid

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


def _tenant_wrap_key(tenant_id: uuid.UUID) -> bytes:
    return hashlib.sha256(b"deployai-private-annotation-wrap-v1" + tenant_id.bytes).digest()


def seal_private_annotation_plaintext(*, tenant_id: uuid.UUID, plaintext: str) -> tuple[bytes, bytes, bytes]:
    """Return ``(nonce, ciphertext, wrapped_dek)`` for storage."""
    dek = os.urandom(32)
    aes = AESGCM(dek)
    nonce = os.urandom(12)
    ct = aes.encrypt(nonce, plaintext.encode("utf-8"), associated_data=tenant_id.bytes)
    wrap_key = AESGCM(_tenant_wrap_key(tenant_id))
    wrap_nonce = os.urandom(12)
    wrapped = wrap_nonce + wrap_key.encrypt(wrap_nonce, dek, b"wrap-dek")
    return nonce, ct, wrapped


def open_private_annotation_ciphertext(
    *,
    tenant_id: uuid.UUID,
    nonce: bytes,
    ciphertext: bytes,
    wrapped_dek: bytes,
) -> str:
    wrap_key = AESGCM(_tenant_wrap_key(tenant_id))
    wn, wct = wrapped_dek[:12], wrapped_dek[12:]
    dek = wrap_key.decrypt(wn, wct, b"wrap-dek")
    aes = AESGCM(dek)
    plain = aes.decrypt(nonce, ciphertext, associated_data=tenant_id.bytes)
    return plain.decode("utf-8")


def foia_private_scope_disclosure_tag(*, annotation_id: uuid.UUID) -> dict[str, str]:
    """Epic 12 hook — tag private-scope rows in FOIA exports."""
    return {
        "scope": "private_override_annotation",
        "annotation_id": str(annotation_id),
        "disclosure": "Author-only strategist note; successor strategists must not see plaintext.",
    }
