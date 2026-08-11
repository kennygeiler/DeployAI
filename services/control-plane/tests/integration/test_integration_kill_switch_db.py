"""Integration coverage for the A8 kill switch against real Postgres.

Exercises the pieces the unit fakes cannot: the ``embedding_jobs``
DELETE and ``ingestion_runs`` UPDATE run against the migrated schema,
and the three phase ledger rows land in ``ledger_events`` with the new
source kinds. Provider HTTP stays mocked via ``httpx.MockTransport``.
"""

from __future__ import annotations

import uuid

import httpx
import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from control_plane.services.integration_kill_switch import disable_integration

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration


def _seed(engine: Engine, *, tid: uuid.UUID, iid: uuid.UUID) -> dict[str, uuid.UUID]:
    """Tenant + gmail integration with tokens + pending queue rows."""
    job_id = uuid.uuid4()
    run_id = uuid.uuid4()
    done_job_id = uuid.uuid4()
    with engine.begin() as c:
        c.execute(text("INSERT INTO app_tenants (id, name) VALUES (:t, 'A8 Tenant')"), {"t": tid})
        c.execute(
            text(
                "INSERT INTO integrations (id, tenant_id, provider, display_name, state, config) "
                "VALUES (:i, :t, 'google_gmail', 'Gmail', 'active', "
                '\'{"oauth": {"refresh_token": "rt-db", "access_token": "at-db"}, '
                '"gmail": {"last_history_id": "77"}}\'::jsonb)'
            ),
            {"i": iid, "t": tid},
        )
        c.execute(
            text(
                "INSERT INTO embedding_jobs (id, tenant_id, source_table, source_id, status) "
                "VALUES (:j, :t, 'matrix_nodes', :s, 'queued'), "
                "       (:d, :t, 'matrix_nodes', :s2, 'done')"
            ),
            {"j": job_id, "t": tid, "s": uuid.uuid4(), "d": done_job_id, "s2": uuid.uuid4()},
        )
        c.execute(
            text(
                "INSERT INTO ingestion_runs (id, tenant_id, integration, status) "
                "VALUES (:r, :t, 'google_gmail', 'running')"
            ),
            {"r": run_id, "t": tid},
        )
    return {"job": job_id, "done_job": done_job_id, "run": run_id}


@pytest.mark.asyncio
async def test_kill_switch_purges_queue_and_lands_phase_ledger_rows(postgres_engine: Engine) -> None:
    tid, iid = uuid.uuid4(), uuid.uuid4()
    seeded = _seed(postgres_engine, tid=tid, iid=iid)

    revoke_calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        revoke_calls.append(request)
        return httpx.Response(200)

    eng = create_async_engine(_async_database_url_from_engine(postgres_engine), future=True)
    mk = async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)
    try:
        async with mk() as session:
            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
                out = await disable_integration(session, iid, http_client=client)
        assert out["ok"] is True
        assert out["oauth_revocation"]["outcome"] == "revoked"
        assert out["queue_purge"]["embedding_jobs_deleted"] == 1
        assert out["queue_purge"]["ingestion_runs_aborted"] == 1
    finally:
        await eng.dispose()

    # Provider got the stored refresh token exactly once.
    assert len(revoke_calls) == 1
    assert b"token=rt-db" in revoke_calls[0].content

    with postgres_engine.connect() as c:
        state, config = c.execute(text("SELECT state, config FROM integrations WHERE id = :i"), {"i": iid}).one()
        assert state == "disabled"
        assert "oauth" not in config
        assert config.get("gmail") == {"last_history_id": "77"}  # non-secret config survives

        # Pending job deleted; completed job untouched.
        remaining = {
            r[0]
            for r in c.execute(
                text("SELECT id FROM embedding_jobs WHERE id IN (:a, :b)"),
                {"a": seeded["job"], "b": seeded["done_job"]},
            )
        }
        assert seeded["job"] not in remaining
        assert seeded["done_job"] in remaining

        run_status, err = c.execute(
            text("SELECT status, error_summary->>'message' FROM ingestion_runs WHERE id = :r"),
            {"r": seeded["run"]},
        ).one()
        assert run_status == "failed"
        assert err == "aborted by integration kill switch"

        kinds = [
            r[0]
            for r in c.execute(
                text(
                    "SELECT source_kind FROM ledger_events "
                    "WHERE tenant_id = :t AND source_kind LIKE 'killswitch_%' "
                    "ORDER BY recorded_at, source_kind"
                ),
                {"t": tid},
            )
        ]
        assert sorted(kinds) == [
            "killswitch_oauth_revoked",
            "killswitch_queue_purged",
            "killswitch_secrets_deleted",
        ]

        # Ledger detail must never carry the token values.
        blobs = [
            r[0]
            for r in c.execute(
                text("SELECT detail::text FROM ledger_events WHERE tenant_id = :t"),
                {"t": tid},
            )
        ]
        for blob in blobs:
            assert "rt-db" not in blob
            assert "at-db" not in blob
