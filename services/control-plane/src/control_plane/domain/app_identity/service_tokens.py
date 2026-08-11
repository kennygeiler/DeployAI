"""ORM + hashing helpers for ``internal_service_tokens`` (pilot-refresh A4).

Per-tenant credentials for the internal API. Historically every internal
caller shared one global ``X-DeployAI-Internal-Key`` and named its tenant via
a client-controlled ``tenant_id`` query param — any key holder could read any
tenant. A tenant-scoped service token binds the caller to exactly one tenant:
:func:`control_plane.config.internal_auth.require_tenant_scoped` rejects any
request whose ``tenant_id`` param does not match the token's tenant.

Storage follows the SCIM bearer pattern (``auth/scim_bearer.py``): the raw
secret is a 24-byte random token shown once at mint time and persisted only
as its SHA-256 hex digest, which doubles as the indexed lookup key. The
digest-equality lookup is safe against timing attacks because the secret is
high-entropy random (not a low-entropy password), matching the existing
``app_tenants.scim_bearer_token_hash`` posture.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Text, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base

RAW_TOKEN_PREFIX = "dpai_svc_"
_RAW_TOKEN_ENTROPY_BYTES = 24


class InternalServiceToken(Base):
    """One tenant-scoped internal-API credential."""

    __tablename__ = "internal_service_tokens"
    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_internal_service_tokens_tenant_name"),
        Index(
            "internal_service_tokens_active",
            "hashed_key",
            unique=True,
            postgresql_where=text("revoked_at IS NULL"),
        ),
        Index(
            "internal_service_tokens_by_tenant",
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
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    hashed_key: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    revoked_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


def generate_raw_token() -> str:
    """Return one freshly-minted raw token: ``dpai_svc_<hex>``."""
    return RAW_TOKEN_PREFIX + secrets.token_hex(_RAW_TOKEN_ENTROPY_BYTES)


def hash_service_token(raw_token: str) -> str:
    """SHA-256 hex digest of the raw token (never log or persist the raw value)."""
    if not isinstance(raw_token, str) or not raw_token:
        raise ValueError("raw_token must be a non-empty string")
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


__all__ = [
    "RAW_TOKEN_PREFIX",
    "InternalServiceToken",
    "generate_raw_token",
    "hash_service_token",
]
