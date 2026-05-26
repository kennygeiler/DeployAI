"""ORM + hashing helpers for ``tenant_api_keys`` (v2 Phase 4, scope-v2 §8.4).

Tenant admins mint API keys for the standalone MCP inbound server. The raw
secret is shown once and persisted only as a scrypt-derived hash. Verification
uses ``hmac.compare_digest`` to stay timing-safe. Keys are scoped to one
engagement (``engagement_id`` non-null at mint time in Phase 4); the column is
nullable to leave the seam open for future tenant-wide keys.

scrypt is from the stdlib (``hashlib.scrypt``); we avoid pulling in
``argon2-cffi``/``bcrypt`` here so the lockfile stays clean. scrypt with
``N=2**14`` is rated against modern offline-cracking attempts on a 24-byte
random secret (≈192 bits of entropy) — and the raw secret itself is the
primary defense; the hash exists so a leaked dump cannot be replayed verbatim.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base

RAW_KEY_PREFIX = "mcp_live_"
_RAW_KEY_ENTROPY_BYTES = 24
_SALT_BYTES = 16
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1
_SCRYPT_DKLEN = 32
_HASH_SCHEME = "scrypt"
_HASH_PARTS = 6


class TenantApiKey(Base):
    """One MCP-server bearer credential bound to a tenant + engagement."""

    __tablename__ = "tenant_api_keys"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_tenant_api_keys_tenant_name"),
        Index(
            "tenant_api_keys_active",
            "hashed_secret",
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "tenant_api_keys_by_tenant",
            "tenant_id",
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=func.gen_random_uuid(),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    engagement_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("engagements.id", ondelete="CASCADE"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    hashed_secret: Mapped[str] = mapped_column(Text(), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(
        ARRAY(Text()),
        nullable=False,
        server_default=text("ARRAY['read']::text[]"),
    )
    last_used_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


def generate_raw_key() -> str:
    """Return one freshly-minted raw key: ``mcp_live_<hex>``."""
    return RAW_KEY_PREFIX + secrets.token_hex(_RAW_KEY_ENTROPY_BYTES)


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _ub64(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def hash_raw_key(raw_key: str) -> str:
    """Hash the raw key via scrypt for at-rest storage.

    Encoded as ``scrypt$<N>$<r>$<p>$<salt_b64>$<derived_b64>`` so verify can
    round-trip the parameters out of the column.
    """
    if not isinstance(raw_key, str) or not raw_key:
        raise ValueError("raw_key must be a non-empty string")
    salt = secrets.token_bytes(_SALT_BYTES)
    derived = hashlib.scrypt(
        raw_key.encode("utf-8"),
        salt=salt,
        n=_SCRYPT_N,
        r=_SCRYPT_R,
        p=_SCRYPT_P,
        dklen=_SCRYPT_DKLEN,
    )
    return f"{_HASH_SCHEME}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}${_b64(salt)}${_b64(derived)}"


def verify_raw_key(raw_key: str, hashed: str) -> bool:
    """Timing-safe verify of ``raw_key`` against the stored ``hashed`` digest.

    Returns ``False`` for any failure mode (mismatch, malformed hash, falsey
    inputs) — never raises.
    """
    if not raw_key or not hashed:
        return False
    parts = hashed.split("$")
    if len(parts) != _HASH_PARTS or parts[0] != _HASH_SCHEME:
        return False
    try:
        n = int(parts[1])
        r = int(parts[2])
        p = int(parts[3])
        salt = _ub64(parts[4])
        expected = _ub64(parts[5])
    except (ValueError, binascii.Error):
        return False
    try:
        candidate = hashlib.scrypt(
            raw_key.encode("utf-8"),
            salt=salt,
            n=n,
            r=r,
            p=p,
            dklen=len(expected),
        )
    except (ValueError, MemoryError):
        return False
    return hmac.compare_digest(candidate, expected)


def constant_time_eq(a: str, b: str) -> bool:
    """Drop-in wrapper around :func:`hmac.compare_digest` for string secrets."""
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


__all__ = [
    "RAW_KEY_PREFIX",
    "TenantApiKey",
    "constant_time_eq",
    "generate_raw_key",
    "hash_raw_key",
    "verify_raw_key",
]
