"""ORM for Story 2-2/2-3: app tenants and provisioned users (Entra/SCIM)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, ForeignKey, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from control_plane.domain.base import Base


class AppTenant(Base):
    """One customer; SCIM bearer token is stored hashed (SHA-256)."""

    __tablename__ = "app_tenants"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    name: Mapped[str] = mapped_column(Text(), nullable=False)
    scim_bearer_token_hash: Mapped[str | None] = mapped_column(Text(), nullable=True, index=True, unique=True)
    tenant_dek_ciphertext: Mapped[str | None] = mapped_column(Text(), nullable=True)
    tenant_dek_key_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    users: Mapped[list[AppUser]] = relationship("AppUser", back_populates="tenant", cascade="all, delete-orphan")


class AppUser(Base):
    __tablename__ = "app_users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=func.gen_random_uuid()
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("app_tenants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    scim_external_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    user_name: Mapped[str] = mapped_column(Text(), nullable=False)
    email: Mapped[str | None] = mapped_column(Text(), nullable=True)
    given_name: Mapped[str | None] = mapped_column(Text(), nullable=True)
    family_name: Mapped[str | None] = mapped_column(Text(), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean(), nullable=False, server_default="true")
    roles: Mapped[Any] = mapped_column(JSONB(), nullable=True)
    entra_sub: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    tenant: Mapped[AppTenant] = relationship("AppTenant", back_populates="users")
