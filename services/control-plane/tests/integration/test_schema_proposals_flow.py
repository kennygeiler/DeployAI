"""Story 1-17: propose → list → promote (scaffold) → list; reject path."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app


def _async_database_url_from_engine(postgres_engine: Engine) -> str:
    # Do not `str`→`make_url` the DSN: that can drop credentials.
    u = postgres_engine.url.set(drivername="postgresql+psycopg")
    return u.render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def internal_client(
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "integration-test-internal")
    monkeypatch.setenv("DEPLOYAI_SCHEMA_PROPOSAL_SCAFFOLD_DIR", str(tmp_path))
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.headers["X-DeployAI-Internal-Key"] = "integration-test-internal"
            yield client
    finally:
        clear_engine_cache()


@pytest.mark.integration
async def test_schema_proposal_promote_writes_scaffold(
    internal_client: AsyncClient,
    tenant_id: uuid.UUID,
    tmp_path: Path,
) -> None:
    proposer = uuid.uuid4()
    rev = uuid.uuid4()
    create = {
        "proposer_actor_id": str(proposer),
        "proposed_ddl": "ALTER TABLE canonical_memory_events ADD COLUMN x text",
        "proposer_agent": "cartographer",
        "proposed_field_path": "events.notes",
        "proposed_type": "text",
        "sample_evidence": {"source": "stub"},
    }
    r = await internal_client.post(
        f"/internal/v1/tenants/{tenant_id}/schema-proposals",
        json=create,
    )
    assert r.status_code == 201, r.text
    prop_id = r.json()["id"]
    r_list = await internal_client.get(
        f"/internal/v1/tenants/{tenant_id}/schema-proposals",
    )
    assert r_list.status_code == 200
    assert len(r_list.json()) == 1

    r2 = await internal_client.post(
        f"/internal/v1/tenants/{tenant_id}/schema-proposals/{prop_id}/promote",
        headers={"X-Deployai-Reviewer-Actor-Id": str(rev)},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["status"] == "promoted"

    p = tmp_path / f"{prop_id}.py"
    assert p.is_file()
    with p.open(encoding="utf-8") as f:
        text = f.read()
    assert "def upgrade" in text
    assert "20260424_0003" in text

    pending = await internal_client.get(
        f"/internal/v1/tenants/{tenant_id}/schema-proposals?status=pending",
    )
    assert pending.json() == []

    prom = await internal_client.get(
        f"/internal/v1/tenants/{tenant_id}/schema-proposals?status=promoted",
    )
    assert len(prom.json()) == 1


@pytest.mark.integration
async def test_schema_proposal_reject(
    internal_client: AsyncClient,
    tenant_id: uuid.UUID,
) -> None:
    proposer = uuid.uuid4()
    rev = uuid.uuid4()
    r = await internal_client.post(
        f"/internal/v1/tenants/{tenant_id}/schema-proposals",
        json={
            "proposer_actor_id": str(proposer),
            "proposed_ddl": "ALTER TABLE t ADD COLUMN w int",
        },
    )
    assert r.status_code == 201
    pid = r.json()["id"]
    rj = await internal_client.post(
        f"/internal/v1/tenants/{tenant_id}/schema-proposals/{pid}/reject",
        headers={"X-Deployai-Reviewer-Actor-Id": str(rev)},
        json={"rejection_reason": "no evidence"},
    )
    assert rj.status_code == 200, rj.text
    data = rj.json()
    assert data["status"] == "rejected"
    assert data["rejection_reason"] == "no evidence"
