"""ORM: tenant_llm_daily_budget (Phase F2.b)."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, ForeignKey, Integer, PrimaryKeyConstraint, text
from sqlalchemy.dialects.postgresql import DATE, UUID
from sqlalchemy.orm import Mapped, mapped_column

from control_plane.domain.base import Base


class TenantLlmDailyBudget(Base):
    """One row per (tenant, day) tracking analyzer LLM token spend."""

    __tablename__ = "tenant_llm_daily_budget"

    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("app_tenants.id"),
        nullable=False,
    )
    usage_date: Mapped[date] = mapped_column(DATE(), nullable=False)
    tokens_used: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        server_default=text("0"),
    )
    daily_cap: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        server_default=text("50000"),
    )

    __table_args__ = (
        PrimaryKeyConstraint("tenant_id", "usage_date"),
        CheckConstraint("tokens_used >= 0", name="tenant_llm_budget_tokens_nonneg"),
        CheckConstraint("daily_cap >= 0", name="tenant_llm_budget_cap_nonneg"),
    )


DEFAULT_DAILY_CAP = 50_000


__all__ = ["DEFAULT_DAILY_CAP", "TenantLlmDailyBudget"]
