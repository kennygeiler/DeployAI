"""Integration: v2 Phase 5 Wave 3H — ``/mcp_killswitch`` internal CP route.

Covers (scope-v2 §9, threat-model §5.5 Option B):

1. ``GET /internal/v1/tenants/{tid}/mcp_killswitch`` returns ``False`` for
   a fresh tenant (server_default applied via Wave 2F migration).
2. ``POST`` with ``{disabled: true}`` flips the column, returns the new
   state, and emits exactly one ``mcp_outbound_killswitch_changed``
   ledger row. The follow-up GET reflects ``True``.
3. ``POST`` on an unknown tenant returns 404 and emits no ledger row.

Run with ``uv run pytest -m integration``.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


def _async_url(eng: Engine) -> str:
    return eng.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(eng: Engine, tid: uuid.UUID, *, name: str = "killswitch-route") -> None:
    with eng.begin() as conn:
        conn.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, :n) ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid), "n": name},
        )


@pytest_asyncio.fixture
async def killswitch_client(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "killswitch-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "killswitch-test-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.mark.asyncio
async def test_get_default_false_then_post_flips_true_and_emits_audit(
    killswitch_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)

    # GET default — Wave 2F migration's server_default applied.
    r = await killswitch_client.get(f"/internal/v1/tenants/{tid}/mcp_killswitch")
    assert r.status_code == 200, r.text
    assert r.json() == {"disabled": False}

    # POST true — flip + audit emit.
    r2 = await killswitch_client.post(
        f"/internal/v1/tenants/{tid}/mcp_killswitch",
        json={"disabled": True},
        headers={"X-DeployAI-Actor-Id": "wave-3h-tester"},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json() == {"disabled": True}

    # GET reflects the new state.
    r3 = await killswitch_client.get(f"/internal/v1/tenants/{tid}/mcp_killswitch")
    assert r3.status_code == 200
    assert r3.json() == {"disabled": True}

    # Exactly one ledger row, with the expected actor + detail.
    with postgres_engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT actor_kind, actor_id, summary, detail::text AS detail_text "
                "FROM ledger_events "
                "WHERE tenant_id = :t AND source_kind = 'mcp_outbound_killswitch_changed'"
            ),
            {"t": str(tid)},
        ).all()
    assert len(rows) == 1, f"expected exactly one killswitch ledger row, got {len(rows)}"
    assert rows[0].actor_kind == "user"
    assert rows[0].actor_id == "wave-3h-tester"
    assert "ENGAGED" in rows[0].summary
    assert '"disabled": true' in rows[0].detail_text


@pytest.mark.asyncio
async def test_post_unknown_tenant_returns_404_and_emits_no_ledger(
    killswitch_client: AsyncClient,
    postgres_engine: Engine,
) -> None:
    unknown_tid = uuid.uuid4()
    r = await killswitch_client.post(
        f"/internal/v1/tenants/{unknown_tid}/mcp_killswitch",
        json={"disabled": True},
    )
    assert r.status_code == 404, r.text
    with postgres_engine.connect() as conn:
        count = conn.execute(
            text(
                "SELECT COUNT(*) FROM ledger_events "
                "WHERE tenant_id = :t AND source_kind = 'mcp_outbound_killswitch_changed'"
            ),
            {"t": str(unknown_tid)},
        ).scalar_one()
    assert count == 0
