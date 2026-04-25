"""Epic 6 Story 6-2: Cartographer extraction payload → canonical ``cartographer.extraction`` row."""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import cast

import pytest
from cartographer.extract import (
    bundle_fingerprint,
    extract_stub,
    extraction_bundle_to_persist_dict,
)
from cartographer.triage import EventSignals, TriageContext, triage_event
from sqlalchemy import select, text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache, tenant_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.services.cartographer_extraction_persist import (
    CARTOGRAPHER_EXTRACTION_TYPE,
    persist_cartographer_extraction,
)

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration
_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "cartographer" / "email_thread.json"


def test_cartographer_extraction_persist_idempotent(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", str(_async_database_url_from_engine(postgres_engine)))
    clear_settings_cache()
    clear_engine_cache()
    try:
        tid = uuid.uuid4()
        eid = uuid.uuid4()
        raw = json.loads(_FIXTURE.read_text(encoding="utf-8"))
        raw["id"] = str(eid)
        event = EventSignals.from_event_dict(raw)
        with postgres_engine.begin() as c:
            c.execute(
                text("INSERT INTO app_tenants (id, name) VALUES (CAST(:t AS uuid), 'carto-extract-test')"),
                {"t": str(tid)},
            )
            c.execute(
                text(
                    """
                    INSERT INTO canonical_memory_events
                        (id, tenant_id, event_type, occurred_at, evidence_span, payload)
                    VALUES
                        (CAST(:eid AS uuid), CAST(:tid AS uuid), 'email.thread', now(), '{}'::jsonb, CAST(:p AS jsonb))
                    """
                ),
                {
                    "eid": str(eid),
                    "tid": str(tid),
                    "p": json.dumps({"fixture": "email_thread", "subject": raw.get("subject")}),
                },
            )

        ctx = TriageContext(
            phase="P5_scale_execution",
            declared_objectives=("NYC DOT deployment schedule and stakeholder alignment with transcript review.",),
            relevance_threshold=0.15,
        )
        triage = triage_event(ctx, event, tenant_id=str(tid))
        assert not triage.triaged_out
        bundle = extract_stub(event, triage)
        fp = bundle_fingerprint(bundle)
        pdict = extraction_bundle_to_persist_dict(bundle)

        async def _run() -> None:
            async with tenant_session(tid) as s:
                assert isinstance(s, AsyncSession)
                a = await persist_cartographer_extraction(
                    s,
                    tenant_id=tid,
                    source_event_id=eid,
                    extraction_payload=pdict,
                    fingerprint=fp,
                )
                b = await persist_cartographer_extraction(
                    s,
                    tenant_id=tid,
                    source_event_id=eid,
                    extraction_payload=pdict,
                    fingerprint=fp,
                )
                assert a is True
                assert b is False
                await s.commit()
            async with tenant_session(tid) as s2:
                r = await s2.execute(
                    select(CanonicalMemoryEvent).where(
                        CanonicalMemoryEvent.tenant_id == tid,
                        CanonicalMemoryEvent.event_type == CARTOGRAPHER_EXTRACTION_TYPE,
                    )
                )
                rows = r.scalars().all()
            assert len(rows) == 1
            pl = cast(dict, rows[0].payload)
            assert pl.get("schema_version")
            assert pl.get("fingerprint") == fp
            ex = pl.get("extraction")
            assert isinstance(ex, dict)
            assert ex.get("entity_count", 0) >= 0

        asyncio.run(_run())
    finally:
        clear_settings_cache()
        clear_engine_cache()
