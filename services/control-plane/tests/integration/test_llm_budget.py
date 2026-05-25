"""Integration: per-tenant daily LLM budget + provenance-analyzer wiring (Phase F2.b)."""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Generator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache, get_app_db_session
from control_plane.domain.base import Base
from control_plane.domain.ledger import (
    LedgerEvent,
    LedgerEventAffects,
    LedgerEventCause,
    TemporalInsight,
)
from control_plane.domain.llm_budget import DEFAULT_DAILY_CAP, TenantLlmDailyBudget
from control_plane.intelligence import decision_provenance_summary as provenance_mod
from control_plane.intelligence.budget import check_and_charge
from control_plane.intelligence.scheduler import run_analyzers
from control_plane.ledger import emit_ledger_event

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _ensure_tables(postgres_engine: Engine) -> Generator[None]:
    tables = [
        Base.metadata.tables[LedgerEvent.__tablename__],
        Base.metadata.tables[LedgerEventCause.__tablename__],
        Base.metadata.tables[LedgerEventAffects.__tablename__],
        Base.metadata.tables[TemporalInsight.__tablename__],
        Base.metadata.tables[TenantLlmDailyBudget.__tablename__],
    ]
    Base.metadata.create_all(postgres_engine, tables=tables, checkfirst=True)
    yield


@pytest_asyncio.fixture
async def _env(postgres_engine: Engine) -> AsyncIterator[None]:
    url = postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)
    os.environ["DATABASE_URL"] = url
    clear_engine_cache()
    yield
    clear_engine_cache()


def _seed_tenant(engine: Engine) -> uuid.UUID:
    tid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'budget-test')"), {"t": str(tid)})
    return tid


def _seed_engagement(engine: Engine, tenant_id: uuid.UUID) -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, 'eng', 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tenant_id)},
        )
    return eid


class _FakeProvider:
    id = "fake-llm"

    def __init__(self, reply: str = "First sentence. Second sentence.") -> None:
        self.reply = reply
        self.calls: list[Any] = []

    def chat_complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        self.calls.append(messages)
        return self.reply

    def embed(self, text: str) -> list[float]:
        return []

    def capabilities(self) -> dict[str, bool]:
        return {}

    async def chat_stream(self, *args: Any, **kwargs: Any) -> Any:
        return None


@pytest.mark.asyncio
async def test_check_and_charge_allows_under_cap_and_rejects_over(postgres_engine: Engine, _env: None) -> None:
    tid = _seed_tenant(postgres_engine)
    async for session in get_app_db_session():
        ok = await check_and_charge(session, tenant_id=tid, estimate=100)
        await session.commit()
        assert ok is True

        ok2 = await check_and_charge(session, tenant_id=tid, estimate=DEFAULT_DAILY_CAP + 1)
        await session.commit()
        assert ok2 is False
        break


@pytest.mark.asyncio
async def test_check_and_charge_creates_row_on_first_hit_and_increments_on_second(
    postgres_engine: Engine, _env: None
) -> None:
    tid = _seed_tenant(postgres_engine)
    moment = datetime(2026, 5, 25, 12, tzinfo=UTC)
    async for session in get_app_db_session():
        before = (
            await session.execute(select(TenantLlmDailyBudget).where(TenantLlmDailyBudget.tenant_id == tid))
        ).scalar_one_or_none()
        assert before is None

        assert await check_and_charge(session, tenant_id=tid, estimate=250, now=moment) is True
        await session.commit()
        first = (
            await session.execute(select(TenantLlmDailyBudget).where(TenantLlmDailyBudget.tenant_id == tid))
        ).scalar_one()
        assert first.usage_date == moment.date()
        assert first.tokens_used == 250
        assert first.daily_cap == DEFAULT_DAILY_CAP

        assert await check_and_charge(session, tenant_id=tid, estimate=400, now=moment) is True
        await session.commit()
        second = (
            await session.execute(select(TenantLlmDailyBudget).where(TenantLlmDailyBudget.tenant_id == tid))
        ).scalar_one()
        assert second.usage_date == moment.date()
        assert second.tokens_used == 650
        break


@pytest.mark.asyncio
async def test_provenance_analyzer_skips_when_budget_exhausted(
    postgres_engine: Engine, _env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    fake = _FakeProvider()
    monkeypatch.setattr(provenance_mod, "get_llm_provider", lambda: fake)

    moment = datetime.now(UTC)
    async for session in get_app_db_session():
        with postgres_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO tenant_llm_daily_budget (tenant_id, usage_date, tokens_used, daily_cap) "
                    "VALUES (:t, :d, :u, :c)"
                ),
                {"t": str(tid), "d": moment.date(), "u": DEFAULT_DAILY_CAP, "c": DEFAULT_DAILY_CAP},
            )

        await _seed_accepted_decision_with_chain(session, tenant_id=tid, engagement_id=eid, at=moment)
        await session.commit()

        writes = await run_analyzers(
            session,
            tenant_id=tid,
            engagement_id=eid,
            analyzer_kinds=["decision_provenance_summary"],
            now=moment + timedelta(minutes=1),
        )
        await session.commit()
        assert writes == []
        assert fake.calls == []
        break


@pytest.mark.asyncio
async def test_provenance_analyzer_uses_tenant_resolved_provider(
    postgres_engine: Engine, _env: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    tid = _seed_tenant(postgres_engine)
    eid = _seed_engagement(postgres_engine, tid)
    env_fake = _FakeProvider("env reply.")
    tenant_fake = _FakeProvider("tenant reply. second sentence.")
    monkeypatch.setattr(provenance_mod, "get_llm_provider", lambda: env_fake)

    async def _resolve(session: Any, tenant_id: uuid.UUID, env_fallback: Any) -> Any:
        assert tenant_id == tid
        return tenant_fake

    monkeypatch.setattr(provenance_mod, "resolve_tenant_llm_provider", _resolve)

    moment = datetime.now(UTC)
    async for session in get_app_db_session():
        await _seed_accepted_decision_with_chain(session, tenant_id=tid, engagement_id=eid, at=moment)
        await session.commit()

        writes = await run_analyzers(
            session,
            tenant_id=tid,
            engagement_id=eid,
            analyzer_kinds=["decision_provenance_summary"],
            now=moment + timedelta(minutes=1),
        )
        await session.commit()

        assert len(writes) == 1
        assert writes[0].narrative == "AI-generated draft: tenant reply. second sentence."
        assert writes[0].metrics["ai_generated"] is True
        assert env_fake.calls == []
        assert len(tenant_fake.calls) == 1

        budget = (
            await session.execute(select(TenantLlmDailyBudget).where(TenantLlmDailyBudget.tenant_id == tid))
        ).scalar_one()
        assert budget.tokens_used > 0
        break


async def _seed_accepted_decision_with_chain(
    session: Any,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    at: datetime,
) -> None:
    proposal_id = uuid.uuid4()
    upstream = await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=at - timedelta(hours=2),
        actor_kind="agent:matrix_extractor",
        actor_id=None,
        source_kind="llm_proposal_created",
        source_ref=proposal_id,
        summary="extract: vendor change",
        detail={"node_type": "decision", "proposal_id": str(proposal_id)},
    )
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=at - timedelta(minutes=5),
        actor_kind="user",
        actor_id=None,
        source_kind="proposal_accepted",
        source_ref=proposal_id,
        summary="accept decision: vendor change",
        detail={"node_type": "decision", "proposal_id": str(proposal_id)},
        caused_by=[upstream.id],
    )
