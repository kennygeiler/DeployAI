"""ORM for Story 2-2/2-3: app tenants and provisioned users (Entra/SCIM)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import TIMESTAMP, Boolean, CheckConstraint, ForeignKey, String, Text, UniqueConstraint, func, text
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


# Allowed provider values; kept in lock-step with the migration's check constraint
# and with `agents/llm.py`'s factory logic. Add a value here + a migration before
# the agent factory can resolve it.
LLM_PROVIDERS: tuple[str, ...] = ("anthropic", "openai", "stub")


class TenantLlmConfig(Base):
    """Per-tenant LLM provider configuration set via the Settings UI.

    One row per tenant (UNIQUE on tenant_id). When absent, the agent
    factory falls back to env defaults (`ANTHROPIC_API_KEY` /
    `DEPLOYAI_LLM_PROVIDER`). API key stored plaintext — acceptable for
    a self-hosted single-team deployment where the customer owns DB +
    host. Multi-tenant hosting should encrypt at rest.
    """

    __tablename__ = "tenant_llm_configs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("deployai_uuid_v7()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    provider: Mapped[str] = mapped_column(Text(), nullable=False)
    model_name: Mapped[str | None] = mapped_column(Text(), nullable=True)
    api_key: Mapped[str | None] = mapped_column(Text(), nullable=True)
    secondary_provider: Mapped[str | None] = mapped_column(String(50), nullable=True)
    secondary_api_key: Mapped[str | None] = mapped_column(Text(), nullable=True)
    secondary_model_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "provider IN ('anthropic', 'openai', 'stub')",
            name="ck_tenant_llm_configs_provider",
        ),
    )


# Allowed agent names for per-tenant prompt overrides; kept in lock-step with
# the migration's check constraint and the resolver in
# `agents/prompts.py`.
AGENT_PROMPT_NAMES: tuple[str, ...] = ("cartographer", "oracle", "master_strategist")


class TenantAgentPrompt(Base):
    """Per-tenant override of an agent's baked-in system prompt.

    One row per (tenant, agent_name). When absent for a given agent, the
    resolver falls back to the default prompt baked into the agent
    module.
    """

    __tablename__ = "tenant_agent_prompts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("deployai_uuid_v7()"),
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    agent_name: Mapped[str] = mapped_column(Text(), nullable=False)
    prompt_text: Mapped[str] = mapped_column(Text(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), server_default=func.now(), nullable=False)

    __table_args__ = (
        CheckConstraint(
            "agent_name IN ('cartographer', 'oracle', 'master_strategist')",
            name="ck_tenant_agent_prompts_agent_name",
        ),
        UniqueConstraint("tenant_id", "agent_name", name="uq_tenant_agent_prompts_tenant_agent"),
    )
