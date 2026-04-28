"""Epic 10 Story 10.1 — override event + learning supersession (integration)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.learnings import LearningState, SolidifiedLearning
from control_plane.domain.canonical_memory.override_payload import (
    OVERRIDE_EVENT_TYPE,
    parse_override_payload,
)
from control_plane.services.learning_override import LearningOverrideError, record_learning_override

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def async_session(postgres_engine: Engine) -> AsyncSession:
    engine = create_async_engine(_async_url(postgres_engine))
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        await session.close()
        await engine.dispose()


@pytest.mark.asyncio
async def test_record_learning_override_persists_canonical_event_and_transitions_state(
    postgres_engine: Engine,
    tenant_id: uuid.UUID,
    async_session: AsyncSession,
) -> None:
    user_id = uuid.uuid4()
    when = datetime(2026, 4, 26, 15, 30, tzinfo=UTC)

    async with async_session.begin():
        ev_a = CanonicalMemoryEvent(
            tenant_id=tenant_id,
            event_type="seed.evidence",
            occurred_at=when,
        )
        ev_b = CanonicalMemoryEvent(
            tenant_id=tenant_id,
            event_type="seed.evidence",
            occurred_at=when,
        )
        async_session.add_all([ev_a, ev_b])
        await async_session.flush()
        learning = SolidifiedLearning(
            tenant_id=tenant_id,
            belief="Original belief",
            evidence_event_ids=[ev_a.id],
            state=LearningState.SOLIDIFIED,
        )
        async_session.add(learning)
        await async_session.flush()
        learning_id = learning.id
        ev_b_id = ev_b.id

    engine = create_async_engine(_async_url(postgres_engine))
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as s2:
            override_event_id = await record_learning_override(
                s2,
                tenant_id=tenant_id,
                user_id=user_id,
                learning_id=learning_id,
                override_evidence_event_ids=[ev_b_id],
                reason_string="Replaced after transcript review (tenant evidence).",
                occurred_at=when,
            )
    finally:
        await engine.dispose()

    with postgres_engine.connect() as conn:
        row = conn.execute(
            text("SELECT event_type, payload FROM canonical_memory_events WHERE id = :id AND tenant_id = :t"),
            {"id": override_event_id, "t": tenant_id},
        ).one()
        assert row.event_type == OVERRIDE_EVENT_TYPE
        parsed = parse_override_payload(row.payload)
        assert parsed.override_id == override_event_id
        assert parsed.user_id == user_id
        assert parsed.learning_id == learning_id
        assert parsed.override_evidence_event_ids == [ev_b_id]

        lr = conn.execute(
            text(
                "SELECT state, supersession_override_event_id, superseding_evidence_event_ids "
                "FROM solidified_learnings WHERE id = :id"
            ),
            {"id": learning_id},
        ).one()
        assert str(lr.state) == "overridden"
        assert lr.supersession_override_event_id == override_event_id
        assert list(lr.superseding_evidence_event_ids) == [ev_b_id]

        lc = conn.execute(
            text(
                "SELECT state FROM learning_lifecycle_states "
                "WHERE learning_id = :l ORDER BY transitioned_at DESC LIMIT 1"
            ),
            {"l": learning_id},
        ).scalar_one()
        assert str(lc) == "overridden"


@pytest.mark.asyncio
async def test_record_learning_override_rejects_wrong_tenant_evidence(
    postgres_engine: Engine,
    tenant_id: uuid.UUID,
    async_session: AsyncSession,
) -> None:
    other = uuid.UUID("00000000-0000-7000-8000-000000000099")
    user_id = uuid.uuid4()
    when = datetime.now(tz=UTC)

    async with async_session.begin():
        ev_own = CanonicalMemoryEvent(
            tenant_id=tenant_id,
            event_type="seed",
            occurred_at=when,
        )
        ev_other = CanonicalMemoryEvent(
            tenant_id=other,
            event_type="seed",
            occurred_at=when,
        )
        async_session.add_all([ev_own, ev_other])
        await async_session.flush()
        learning = SolidifiedLearning(
            tenant_id=tenant_id,
            belief="Belief",
            evidence_event_ids=[ev_own.id],
            state=LearningState.SOLIDIFIED,
        )
        async_session.add(learning)
        await async_session.flush()
        learning_id = learning.id

    engine = create_async_engine(_async_url(postgres_engine))
    try:
        async with async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)() as s2:
            with pytest.raises(LearningOverrideError, match="evidence"):
                await record_learning_override(
                    s2,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    learning_id=learning_id,
                    override_evidence_event_ids=[ev_other.id],
                    reason_string="Cross-tenant evidence must be rejected.",
                )
    finally:
        await engine.dispose()
