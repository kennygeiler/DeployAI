"""Story 3-6: duplicate ``ingestion_dedup_key`` does not create two rows."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache, tenant_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.infra.canonical_idempotent_write import try_insert_with_ingestion_dedup

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration


def test_idempotent_dedup_second_insert_skipped(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    u = str(_async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DATABASE_URL", u)
    clear_settings_cache()
    clear_engine_cache()
    try:
        tid = uuid.uuid4()
        with postgres_engine.begin() as c:
            c.execute(
                text("INSERT INTO app_tenants (id, name) VALUES (CAST(:t AS uuid), 'i-dedup')"),
                {"t": str(tid)},
            )
        import asyncio

        async def _run() -> None:
            dedup = "m365:calendar_event:e1:v1"
            now = datetime.now(UTC)
            async with tenant_session(tid) as s:
                assert isinstance(s, AsyncSession)
                a = await try_insert_with_ingestion_dedup(
                    s,
                    tenant_id=tid,
                    event_type="calendar.event",
                    occurred_at=now,
                    source_ref="graph:calendar_event:e1",
                    payload={"x": 1},
                    ingestion_dedup_key=dedup,
                )
                b = await try_insert_with_ingestion_dedup(
                    s,
                    tenant_id=tid,
                    event_type="calendar.event",
                    occurred_at=now,
                    source_ref="graph:calendar_event:e1",
                    payload={"x": 2},
                    ingestion_dedup_key=dedup,
                )
                assert a is True
                assert b is False
                await s.commit()
            async with tenant_session(tid) as s2:
                r = await s2.execute(
                    select(CanonicalMemoryEvent).where(
                        CanonicalMemoryEvent.tenant_id == tid,
                        CanonicalMemoryEvent.ingestion_dedup_key == dedup,
                    )
                )
                rows = r.scalars().all()
            assert len(rows) == 1
            assert (rows[0].payload or {}).get("x") == 1

        asyncio.run(_run())
    finally:
        clear_settings_cache()
        clear_engine_cache()
