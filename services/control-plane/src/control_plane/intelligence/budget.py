"""Per-tenant daily LLM token budget for analyzers (Phase F2.b).

LLM-assisted analyzers call :func:`check_and_charge` before any LLM
request. Returns ``True`` when the estimated tokens fit under
``daily_cap`` and atomically charges the row; returns ``False`` when
budget is exhausted so the caller can degrade gracefully.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.llm_budget import DEFAULT_DAILY_CAP, TenantLlmDailyBudget


async def check_and_charge(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    estimate: int,
    now: datetime | None = None,
) -> bool:
    """Atomically check + charge today's budget. ``False`` when exhausted.

    Two-step: INSERT-OR-NOTHING (creates today's row on first hit), then
    SELECT ... FOR UPDATE to take a row lock, then check + UPDATE inside
    the same transaction. The row lock is what makes concurrent callers
    serialize on the budget check, not the WHERE-clause atomicity of
    UPDATE on its own.
    """
    if estimate < 0:
        raise ValueError("estimate must be non-negative")
    today = (now or datetime.now(UTC)).astimezone(UTC).date()
    await _ensure_row(session, tenant_id=tenant_id, usage_date=today)
    return await _try_charge(session, tenant_id=tenant_id, usage_date=today, estimate=estimate)


async def _ensure_row(session: AsyncSession, *, tenant_id: uuid.UUID, usage_date: date) -> None:
    stmt = (
        pg_insert(TenantLlmDailyBudget)
        .values(
            tenant_id=tenant_id,
            usage_date=usage_date,
            tokens_used=0,
            daily_cap=DEFAULT_DAILY_CAP,
        )
        .on_conflict_do_nothing(index_elements=["tenant_id", "usage_date"])
    )
    await session.execute(stmt)


async def _try_charge(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    usage_date: date,
    estimate: int,
) -> bool:
    from sqlalchemy import update

    lock_stmt = (
        select(TenantLlmDailyBudget.tokens_used, TenantLlmDailyBudget.daily_cap)
        .where(
            TenantLlmDailyBudget.tenant_id == tenant_id,
            TenantLlmDailyBudget.usage_date == usage_date,
        )
        .with_for_update()
    )
    row = (await session.execute(lock_stmt)).one_or_none()
    if row is None:
        return False
    tokens_used, daily_cap = row
    if tokens_used + estimate > daily_cap:
        return False

    update_stmt = (
        update(TenantLlmDailyBudget)
        .where(
            TenantLlmDailyBudget.tenant_id == tenant_id,
            TenantLlmDailyBudget.usage_date == usage_date,
        )
        .values(tokens_used=TenantLlmDailyBudget.tokens_used + estimate)
    )
    await session.execute(update_stmt)
    await session.flush()
    return True


__all__ = ["check_and_charge"]
