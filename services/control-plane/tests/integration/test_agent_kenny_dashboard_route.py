"""Integration: Phase 6 Wave C — Agent Kenny telemetry dashboard route.

Covers scope-v2 §11.4:

1. Auth: missing internal API key → 401.
2. Tenant not found → 404 before any DB read.
3. Happy path: seeded mix of audit traces + agent_tool_invocation +
   oracle_chat_turn (with caused_by edges) + lint_flags returns the
   expected aggregate document — hallucination rate, latency percentiles,
   IDK rate, tool-call distribution, lint kind breakdown, top-cited
   events, adversarial concerns total.
4. Tenant isolation: rows in tenant B never affect tenant A's response.
5. Window filter: rows older than ``window_days`` are excluded.

Run with ``uv run pytest -m integration``.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(
        hide_password=False,
    )


def _ins_tenant(engine: Engine, tid: uuid.UUID, *, name: str) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, :n) ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid), "n": name},
        )


def _ins_engagement(engine: Engine, *, tenant_id: uuid.UUID, eid: uuid.UUID, name: str) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO engagements (id, tenant_id, name)
                VALUES (:e, :t, :n)
                ON CONFLICT (id) DO NOTHING
                """,
            ),
            {"e": str(eid), "t": str(tenant_id), "n": name},
        )


def _ins_audit_trace(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    turn_id: uuid.UUID,
    total_citations: int,
    unverified_count: int,
    adversarial_concerns_count: int,
    duration_ms: float,
    final_text: str,
    created_at: datetime,
    tool_calls_count: int = 0,
) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO agent_audit_traces
                    (tenant_id, engagement_id, turn_id, total_citations,
                     unverified_count, adversarial_concerns_count,
                     tool_calls_count, duration_ms, final_text, created_at)
                VALUES
                    (:t, :e, :turn, :tc, :uv, :ac, :tlc, :dur, :ft, :ca)
                """,
            ),
            {
                "t": str(tenant_id),
                "e": str(engagement_id),
                "turn": str(turn_id),
                "tc": total_citations,
                "uv": unverified_count,
                "ac": adversarial_concerns_count,
                "tlc": tool_calls_count,
                "dur": duration_ms,
                "ft": final_text,
                "ca": created_at,
            },
        )


def _ins_ledger(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID | None,
    occurred_at: datetime,
    actor_kind: str,
    actor_id: str | None,
    source_kind: str,
    summary: str,
    detail: dict[str, object] | None = None,
    event_id: uuid.UUID | None = None,
) -> uuid.UUID:
    eid = event_id or uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO ledger_events
                    (id, tenant_id, engagement_id, occurred_at, actor_kind,
                     actor_id, source_kind, summary, detail)
                VALUES
                    (:id, :tid, :eid, :occ, :ak, :aid, :sk, :sm, CAST(:det AS jsonb))
                """,
            ),
            {
                "id": str(eid),
                "tid": str(tenant_id),
                "eid": str(engagement_id) if engagement_id else None,
                "occ": occurred_at,
                "ak": actor_kind,
                "aid": actor_id,
                "sk": source_kind,
                "sm": summary,
                "det": json.dumps(detail or {}, default=str),
            },
        )
    return eid


def _ins_cause(engine: Engine, *, event_id: uuid.UUID, caused_by_id: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO ledger_event_causes (event_id, caused_by_id)
                VALUES (:e, :c)
                ON CONFLICT DO NOTHING
                """,
            ),
            {"e": str(event_id), "c": str(caused_by_id)},
        )


def _ins_lint_flag(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    kind: str,
    flagged_at: datetime,
    target_kind: str = "matrix_node",
    target_id: uuid.UUID | None = None,
) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                """
                INSERT INTO lint_flags
                    (tenant_id, engagement_id, kind, target_kind,
                     target_id, flagged_at)
                VALUES (:t, :e, :k, :tk, :ti, :fa)
                """,
            ),
            {
                "t": str(tenant_id),
                "e": str(engagement_id),
                "k": kind,
                "tk": target_kind,
                "ti": str(target_id or uuid.uuid4()),
                "fa": flagged_at,
            },
        )


@pytest_asyncio.fixture
async def dashboard_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "kenny-dashboard-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "kenny-dashboard-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_missing_internal_key_returns_401(
    dashboard_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid, name="kenny-dash-auth")
    r = await dashboard_client.get(
        f"/internal/v1/tenants/{tid}/agent_kenny_dashboard",
        headers={"X-DeployAI-Internal-Key": ""},
    )
    assert r.status_code == 401, r.text


@pytest.mark.asyncio
async def test_unknown_tenant_returns_404(dashboard_client: AsyncClient) -> None:
    r = await dashboard_client.get(f"/internal/v1/tenants/{uuid.uuid4()}/agent_kenny_dashboard")
    assert r.status_code == 404, r.text


@pytest.mark.asyncio
async def test_happy_path_aggregations(
    dashboard_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    """Seed a realistic mix and verify every dashboard field comes back right."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid, name="kenny-dash-happy")
    _ins_engagement(postgres_engine, tenant_id=tid, eid=eid, name="happy-eng")

    now = datetime.now(UTC)
    inside = now - timedelta(hours=1)

    # 4 audit traces:
    #  - 2 with verified citations only
    #  - 1 with 2/5 unverified
    #  - 1 with 0 citations (IDK turn) + concerns
    _ins_audit_trace(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        turn_id=uuid.uuid4(),
        total_citations=4,
        unverified_count=0,
        adversarial_concerns_count=0,
        duration_ms=200.0,
        final_text="Here is the answer based on [event:abc].",
        created_at=inside,
    )
    _ins_audit_trace(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        turn_id=uuid.uuid4(),
        total_citations=3,
        unverified_count=0,
        adversarial_concerns_count=0,
        duration_ms=400.0,
        final_text="Reply with citations [event:def].",
        created_at=inside,
    )
    _ins_audit_trace(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        turn_id=uuid.uuid4(),
        total_citations=5,
        unverified_count=2,
        adversarial_concerns_count=1,
        duration_ms=800.0,
        final_text="Partial reply [event:ghi].",
        created_at=inside,
    )
    _ins_audit_trace(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        turn_id=uuid.uuid4(),
        total_citations=0,
        unverified_count=0,
        adversarial_concerns_count=2,
        duration_ms=1500.0,
        final_text="I don't know — that's not in this engagement.",
        created_at=inside,
    )

    # 3 tool calls — matrix.query x2, ledger.search x1
    for _ in range(2):
        _ins_ledger(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            occurred_at=inside,
            actor_kind="agent",
            actor_id="kenny",
            source_kind="agent_tool_invocation",
            summary="tool:matrix.query rows=10 dur=42ms",
            detail={"tool_name": "matrix.query", "row_count": 10, "duration_ms": 42},
        )
    _ins_ledger(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=inside,
        actor_kind="agent",
        actor_id="kenny",
        source_kind="agent_tool_invocation",
        summary="tool:ledger.search rows=5 dur=80ms",
        detail={"tool_name": "ledger.search", "row_count": 5, "duration_ms": 80},
    )

    # 2 lint flags: contradiction + stale
    _ins_lint_flag(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="contradiction",
        flagged_at=inside,
    )
    _ins_lint_flag(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="stale",
        flagged_at=inside,
    )
    _ins_lint_flag(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="contradiction",
        flagged_at=inside,
    )

    # Top-cited: seed two source events + two oracle_chat_turn rows that
    # cite them. Event A is cited by both turns; event B only by one.
    src_a = _ins_ledger(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=inside - timedelta(days=2),
        actor_kind="user",
        actor_id="u-1",
        source_kind="email_ingest",
        summary="Email: kickoff for project X",
    )
    src_b = _ins_ledger(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=inside - timedelta(days=3),
        actor_kind="user",
        actor_id="u-1",
        source_kind="meeting_webhook",
        summary="Meeting: weekly sync",
    )
    turn_evt_1 = _ins_ledger(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=inside,
        actor_kind="agent:kenny",
        actor_id=str(uuid.uuid4()),
        source_kind="oracle_chat_turn",
        summary="kenny v2 reply (100 tokens, 1 tools)",
    )
    turn_evt_2 = _ins_ledger(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        occurred_at=inside,
        actor_kind="agent:kenny",
        actor_id=str(uuid.uuid4()),
        source_kind="oracle_chat_turn",
        summary="kenny v2 reply (150 tokens, 2 tools)",
    )
    _ins_cause(postgres_engine, event_id=turn_evt_1, caused_by_id=src_a)
    _ins_cause(postgres_engine, event_id=turn_evt_1, caused_by_id=src_b)
    _ins_cause(postgres_engine, event_id=turn_evt_2, caused_by_id=src_a)

    r = await dashboard_client.get(f"/internal/v1/tenants/{tid}/agent_kenny_dashboard?window_days=7")
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["window_days"] == 7
    # 2 unverified / 12 total citations
    assert body["citations_total"] == 12
    assert body["citations_unverified"] == 2
    assert abs(body["hallucination_rate"] - (2.0 / 12.0)) < 1e-3
    # 1 of 4 turns says "I don't know"
    assert abs(body["idk_rate"] - 0.25) < 1e-3
    # 3 concerns total (0 + 0 + 1 + 2)
    assert body["adversarial_concerns_total"] == 3
    # latencies — p50 between 400 and 800, p99 close to 1500
    assert 200 <= body["latency_p50_ms"] <= 800
    assert body["latency_p99_ms"] >= 1000

    # Tool calls ordered by count desc.
    tools = body["tool_calls"]
    assert {t["tool"] for t in tools} == {"matrix.query", "ledger.search"}
    top_tool = tools[0]
    assert top_tool["tool"] == "matrix.query"
    assert top_tool["count"] == 2

    # Lint flag breakdown: contradiction (2) > stale (1).
    lint = body["lint_flag_counts"]
    kinds = {row["kind"]: row["count"] for row in lint}
    assert kinds.get("contradiction") == 2
    assert kinds.get("stale") == 1
    # The contradiction row should be sorted first (count desc).
    assert lint[0]["kind"] == "contradiction"

    # Top-cited: event A first (2 citations), event B second (1).
    cited = body["top_cited_events"]
    assert len(cited) == 2
    assert cited[0]["event_id"] == str(src_a)
    assert cited[0]["citation_count"] == 2
    assert cited[1]["event_id"] == str(src_b)
    assert cited[1]["citation_count"] == 1
    assert "kickoff" in cited[0]["summary"]


@pytest.mark.asyncio
async def test_tenant_isolation(
    dashboard_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid_a = uuid.uuid4()
    tid_b = uuid.uuid4()
    eid_a = uuid.uuid4()
    eid_b = uuid.uuid4()
    _ins_tenant(postgres_engine, tid_a, name="kenny-dash-iso-a")
    _ins_tenant(postgres_engine, tid_b, name="kenny-dash-iso-b")
    _ins_engagement(postgres_engine, tenant_id=tid_a, eid=eid_a, name="iso-a")
    _ins_engagement(postgres_engine, tenant_id=tid_b, eid=eid_b, name="iso-b")

    now = datetime.now(UTC)

    # Heavy traffic on tenant B that MUST NOT bleed into tenant A's reply.
    for _ in range(5):
        _ins_audit_trace(
            postgres_engine,
            tenant_id=tid_b,
            engagement_id=eid_b,
            turn_id=uuid.uuid4(),
            total_citations=10,
            unverified_count=10,
            adversarial_concerns_count=5,
            duration_ms=9000.0,
            final_text="something",
            created_at=now,
        )
        _ins_ledger(
            postgres_engine,
            tenant_id=tid_b,
            engagement_id=eid_b,
            occurred_at=now,
            actor_kind="agent",
            actor_id="kenny",
            source_kind="agent_tool_invocation",
            summary="tool:matrix.query rows=10",
            detail={"tool_name": "matrix.query"},
        )
        _ins_lint_flag(
            postgres_engine,
            tenant_id=tid_b,
            engagement_id=eid_b,
            kind="contradiction",
            flagged_at=now,
        )

    # Tenant A has one quiet turn with no citations.
    _ins_audit_trace(
        postgres_engine,
        tenant_id=tid_a,
        engagement_id=eid_a,
        turn_id=uuid.uuid4(),
        total_citations=0,
        unverified_count=0,
        adversarial_concerns_count=0,
        duration_ms=100.0,
        final_text="ack",
        created_at=now,
    )

    r = await dashboard_client.get(f"/internal/v1/tenants/{tid_a}/agent_kenny_dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["citations_total"] == 0
    assert body["citations_unverified"] == 0
    assert body["hallucination_rate"] == 0.0
    assert body["tool_calls"] == []
    assert body["lint_flag_counts"] == []
    assert body["top_cited_events"] == []
    assert body["adversarial_concerns_total"] == 0


@pytest.mark.asyncio
async def test_window_excludes_old_rows(
    dashboard_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    """Rows outside ``window_days`` must not contribute to aggregates."""
    tid = uuid.uuid4()
    eid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid, name="kenny-dash-window")
    _ins_engagement(postgres_engine, tenant_id=tid, eid=eid, name="window-eng")

    now = datetime.now(UTC)
    far_past = now - timedelta(days=30)
    recent = now - timedelta(hours=2)

    # Old: must be filtered out by window_days=1.
    _ins_audit_trace(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        turn_id=uuid.uuid4(),
        total_citations=10,
        unverified_count=10,
        adversarial_concerns_count=10,
        duration_ms=5000.0,
        final_text="stale row",
        created_at=far_past,
    )
    _ins_lint_flag(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        kind="contradiction",
        flagged_at=far_past,
    )

    # Recent: contributes.
    _ins_audit_trace(
        postgres_engine,
        tenant_id=tid,
        engagement_id=eid,
        turn_id=uuid.uuid4(),
        total_citations=2,
        unverified_count=0,
        adversarial_concerns_count=0,
        duration_ms=150.0,
        final_text="fresh reply",
        created_at=recent,
    )

    r = await dashboard_client.get(f"/internal/v1/tenants/{tid}/agent_kenny_dashboard?window_days=1")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["citations_total"] == 2
    assert body["citations_unverified"] == 0
    assert body["adversarial_concerns_total"] == 0
    assert body["lint_flag_counts"] == []
