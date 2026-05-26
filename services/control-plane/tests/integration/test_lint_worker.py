"""Integration: v2 Phase 0.6 lint worker (scope-v2 §4).

Covers each lint kind end-to-end against a live testcontainer:
  - Orphan: delete a source ledger event a kenny insight cites; /run flags it.
  - Missing cite: a matrix_node description with an uncited paragraph.
  - Broken cite: a kenny insight body cites a fabricated UUID.
  - Stale: a 35-day-old insight whose source event has a newer descendant.
  - Contradiction: two kenny insights with overlapping cites, opposite stance.

Plus:
  - Resolve endpoint flips ``resolved_at`` and filters from the default list.
  - Cross-engagement isolation: flagging in engagement A does not show in B.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache, get_app_db_session
from control_plane.ledger import emit_ledger_event
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'lint-test') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_engagement(engine: Engine, tenant_id: uuid.UUID, name: str = "lint-eng") -> uuid.UUID:
    eid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO engagements (id, tenant_id, name, current_phase, status) "
                "VALUES (:i, :t, :n, 'P1_pre_engagement', 'active')"
            ),
            {"i": str(eid), "t": str(tenant_id), "n": name},
        )
    return eid


def _ins_matrix_node(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    node_type: str,
    title: str,
    description: str | None = None,
) -> uuid.UUID:
    nid = uuid.uuid4()
    attrs = "{}"
    if description is not None:
        import json as _json

        attrs = _json.dumps({"description": description})
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_nodes "
                "(id, tenant_id, engagement_id, node_type, title, attributes, evidence_event_ids) "
                "VALUES (:i, :t, :e, :nt, :ti, CAST(:a AS jsonb), '{}'::uuid[])"
            ),
            {
                "i": str(nid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "nt": node_type,
                "ti": title,
                "a": attrs,
            },
        )
    return nid


def _ins_ledger_event(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    source_kind: str = "manual_capture",
    summary: str = "seed event",
    occurred_at: datetime | None = None,
) -> uuid.UUID:
    eid = uuid.uuid4()
    ts = (occurred_at or datetime.now(UTC)).isoformat()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO ledger_events "
                "(id, tenant_id, engagement_id, occurred_at, actor_kind, source_kind, summary, detail) "
                "VALUES (:i, :t, :e, CAST(:o AS timestamptz), 'user', :sk, :s, '{}'::jsonb)"
            ),
            {
                "i": str(eid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "o": ts,
                "sk": source_kind,
                "s": summary,
            },
        )
    return eid


def _ins_ledger_cause(engine: Engine, *, event_id: uuid.UUID, caused_by_id: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO ledger_event_causes (event_id, caused_by_id) VALUES (:e, :c) ON CONFLICT DO NOTHING"),
            {"e": str(event_id), "c": str(caused_by_id)},
        )


def _ins_kenny_insight(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    body: str,
    citation_event_ids: list[uuid.UUID],
    citation_node_ids: list[uuid.UUID] | None = None,
    title: str = "Decision provenance",
    last_refreshed_at: datetime | None = None,
) -> uuid.UUID:
    iid = uuid.uuid4()
    refreshed = (last_refreshed_at or datetime.now(UTC)).isoformat()
    node_ids = "{" + ",".join(str(n) for n in (citation_node_ids or [])) + "}"
    event_ids = "{" + ",".join(str(e) for e in citation_event_ids) + "}"
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_insights "
                "(id, tenant_id, engagement_id, agent, insight_type, severity, title, body, "
                " citation_node_ids, citation_edge_ids, citation_event_ids, dedup_key, status, "
                " last_refreshed_at, stale) "
                "VALUES (:i, :t, :e, 'kenny', 'decision_provenance_summary', 'medium', :ti, :b, "
                "        CAST(:nids AS uuid[]), '{}'::uuid[], CAST(:eids AS uuid[]), :k, 'open', "
                "        CAST(:r AS timestamptz), false)"
            ),
            {
                "i": str(iid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "ti": title,
                "b": body,
                "nids": node_ids,
                "eids": event_ids,
                "k": f"kenny:lint-test:{iid}",
                "r": refreshed,
            },
        )
    return iid


@pytest_asyncio.fixture
async def l_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "lint-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test", timeout=60.0)
    client.headers["X-DeployAI-Internal-Key"] = "lint-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_orphan_flag_when_source_event_deleted(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    ev = _ins_ledger_event(postgres_engine, tenant_id=tid, engagement_id=eid)
    body = f"The decision was approved [event:{ev}]."
    insight_id = _ins_kenny_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        body=body,
        citation_event_ids=[ev],
    )
    # Delete the source event — orphan insight remains.
    with postgres_engine.begin() as c:
        c.execute(text("DELETE FROM ledger_events WHERE id = :e"), {"e": str(ev)})

    resp = await l_client.post(f"/internal/v1/admin/lint/run?tenant_id={tid}&engagement_id={eid}")
    assert resp.status_code == 200, resp.text
    body_json = resp.json()
    assert body_json["flag_count"] >= 1
    assert body_json["by_kind"].get("orphan", 0) >= 1

    listing = await l_client.get(f"/internal/v1/admin/lint/flags?tenant_id={tid}&engagement_id={eid}&kind=orphan")
    assert listing.status_code == 200, listing.text
    flags = listing.json()["flags"]
    orphan_for_insight = [f for f in flags if f["target_id"] == str(insight_id)]
    assert orphan_for_insight, "expected an orphan flag against the insight whose source was deleted"
    detail = orphan_for_insight[0]["detail"]
    assert str(ev) in detail["missing_event_ids"]


@pytest.mark.asyncio
async def test_missing_cite_flag_on_uncited_paragraph(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    ev = _ins_ledger_event(postgres_engine, tenant_id=tid, engagement_id=eid)
    description = (
        f"First paragraph carries a cite [event:{ev}].\n\n"
        "Second paragraph forgets to cite anything at all.\n\n"
        f"Third paragraph cites again [event:{ev}]."
    )
    node_id = _ins_matrix_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="decision",
        title="missing-cite test",
        description=description,
    )

    resp = await l_client.post(f"/internal/v1/admin/lint/run?tenant_id={tid}&engagement_id={eid}")
    assert resp.status_code == 200, resp.text
    body_json = resp.json()
    assert body_json["by_kind"].get("missing_cite", 0) >= 1

    listing = await l_client.get(f"/internal/v1/admin/lint/flags?tenant_id={tid}&engagement_id={eid}&kind=missing_cite")
    assert listing.status_code == 200, listing.text
    flags = listing.json()["flags"]
    paragraph_flags = [f for f in flags if f["target_id"] == str(node_id)]
    assert paragraph_flags, "expected a missing_cite flag for the uncited paragraph"
    assert paragraph_flags[0]["detail"]["paragraph_index"] == 1


@pytest.mark.asyncio
async def test_broken_cite_flag_on_fabricated_uuid(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    real_ev = _ins_ledger_event(postgres_engine, tenant_id=tid, engagement_id=eid)
    bogus_ev = uuid.uuid4()
    body = (
        f"First paragraph cites a real event [event:{real_ev}].\n\n"
        f"Second paragraph cites a fabricated event [event:{bogus_ev}]."
    )
    insight_id = _ins_kenny_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        body=body,
        citation_event_ids=[real_ev],
    )

    resp = await l_client.post(f"/internal/v1/admin/lint/run?tenant_id={tid}&engagement_id={eid}")
    assert resp.status_code == 200, resp.text
    body_json = resp.json()
    assert body_json["by_kind"].get("broken_cite", 0) >= 1

    listing = await l_client.get(f"/internal/v1/admin/lint/flags?tenant_id={tid}&engagement_id={eid}&kind=broken_cite")
    flags = listing.json()["flags"]
    broken = [f for f in flags if f["target_id"] == str(insight_id) and f["detail"].get("citation_id") == str(bogus_ev)]
    assert broken, "expected a broken_cite flag for the fabricated UUID"


@pytest.mark.asyncio
async def test_stale_flag_when_descendant_event_newer(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    long_ago = datetime.now(UTC) - timedelta(days=40)
    just_now = datetime.now(UTC)
    source_ev = _ins_ledger_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=long_ago,
    )
    descendant_ev = _ins_ledger_event(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=just_now,
        summary="newer descendant event",
    )
    _ins_ledger_cause(postgres_engine, event_id=descendant_ev, caused_by_id=source_ev)
    body = f"Old summary [event:{source_ev}]."
    insight_id = _ins_kenny_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        body=body,
        citation_event_ids=[source_ev],
        last_refreshed_at=long_ago,
    )

    resp = await l_client.post(f"/internal/v1/admin/lint/run?tenant_id={tid}&engagement_id={eid}")
    assert resp.status_code == 200, resp.text
    body_json = resp.json()
    assert body_json["by_kind"].get("stale", 0) >= 1

    with postgres_engine.connect() as c:
        stale_row = (
            c.execute(
                text("SELECT stale FROM matrix_insights WHERE id = :i"),
                {"i": str(insight_id)},
            )
            .mappings()
            .first()
        )
        assert stale_row is not None
        assert stale_row["stale"] is True


@pytest.mark.asyncio
async def test_contradiction_flag_for_opposite_stance_insights(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    ev = _ins_ledger_event(postgres_engine, tenant_id=tid, engagement_id=eid)
    decision_node = _ins_matrix_node(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        node_type="decision",
        title="AD migration",
    )

    _ins_kenny_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        body=f"The steering committee approved the migration plan [event:{ev}].",
        citation_event_ids=[ev],
        citation_node_ids=[decision_node],
        title="approval narrative",
    )
    _ins_kenny_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        body=f"The migration was later rejected on cost grounds [event:{ev}].",
        citation_event_ids=[ev],
        citation_node_ids=[decision_node],
        title="rejection narrative",
    )

    resp = await l_client.post(f"/internal/v1/admin/lint/run?tenant_id={tid}&engagement_id={eid}")
    assert resp.status_code == 200, resp.text
    body_json = resp.json()
    assert body_json["by_kind"].get("contradiction", 0) >= 1


@pytest.mark.asyncio
async def test_resolve_endpoint_filters_from_default_listing(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    ev = _ins_ledger_event(postgres_engine, tenant_id=tid, engagement_id=eid)
    _ins_kenny_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        body=f"Approved [event:{ev}].",
        citation_event_ids=[ev],
    )
    with postgres_engine.begin() as c:
        c.execute(text("DELETE FROM ledger_events WHERE id = :e"), {"e": str(ev)})

    resp = await l_client.post(f"/internal/v1/admin/lint/run?tenant_id={tid}&engagement_id={eid}")
    assert resp.status_code == 200, resp.text

    listing = await l_client.get(f"/internal/v1/admin/lint/flags?tenant_id={tid}&engagement_id={eid}")
    flags = listing.json()["flags"]
    assert flags, "expected at least one open flag before resolve"
    flag_id = flags[0]["id"]

    resolved = await l_client.post(f"/internal/v1/admin/lint/flags/{flag_id}/resolve?tenant_id={tid}")
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["resolved_at"] is not None

    listing_open = await l_client.get(f"/internal/v1/admin/lint/flags?tenant_id={tid}&engagement_id={eid}")
    open_ids = {f["id"] for f in listing_open.json()["flags"]}
    assert flag_id not in open_ids

    listing_resolved = await l_client.get(
        f"/internal/v1/admin/lint/flags?tenant_id={tid}&engagement_id={eid}&resolved=true"
    )
    resolved_ids = {f["id"] for f in listing_resolved.json()["flags"]}
    assert flag_id in resolved_ids


@pytest.mark.asyncio
async def test_cross_engagement_isolation(l_client: AsyncClient, postgres_engine: Engine) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eng_a = _ins_engagement(postgres_engine, tid, name="lint-eng-A")
    eng_b = _ins_engagement(postgres_engine, tid, name="lint-eng-B")

    ev_a = _ins_ledger_event(postgres_engine, tenant_id=tid, engagement_id=eng_a)
    _ins_kenny_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eng_a,
        body=f"Approved [event:{ev_a}].",
        citation_event_ids=[ev_a],
    )
    with postgres_engine.begin() as c:
        c.execute(text("DELETE FROM ledger_events WHERE id = :e"), {"e": str(ev_a)})

    resp = await l_client.post(f"/internal/v1/admin/lint/run?tenant_id={tid}&engagement_id={eng_a}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["flag_count"] >= 1

    listing_b = await l_client.get(f"/internal/v1/admin/lint/flags?tenant_id={tid}&engagement_id={eng_b}")
    assert listing_b.status_code == 200, listing_b.text
    assert listing_b.json()["flags"] == []


@pytest.mark.asyncio
async def test_event_triggered_inline_lint_runs_on_insight_opened(
    l_client: AsyncClient, postgres_engine: Engine
) -> None:
    """Emitter dispatch: an insight_opened ledger event runs lint inline so
    follow-up substrate writes do not need a manual /run call to surface issues.
    """
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    eid = _ins_engagement(postgres_engine, tid)
    ev = _ins_ledger_event(postgres_engine, tenant_id=tid, engagement_id=eid)
    _ins_kenny_insight(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        body=f"Approved [event:{ev}].",
        citation_event_ids=[ev],
    )
    with postgres_engine.begin() as c:
        c.execute(text("DELETE FROM ledger_events WHERE id = :e"), {"e": str(ev)})

    async for session in get_app_db_session():
        await emit_ledger_event(
            session,
            tenant_id=tid,
            engagement_id=eid,
            occurred_at=datetime.now(UTC),
            actor_kind="user",
            actor_id="lint-trigger",
            source_kind="insight_opened",
            source_ref=None,
            summary="trigger lint dispatch",
            detail={},
        )
        await session.commit()
        break

    listing = await l_client.get(f"/internal/v1/admin/lint/flags?tenant_id={tid}&engagement_id={eid}")
    flags = listing.json()["flags"]
    kinds = {f["kind"] for f in flags}
    assert "orphan" in kinds, f"expected inline orphan flag from emitter dispatch, got {kinds}"


# Touch dynamic typing helpers used in fixture setup.
_ = Any
