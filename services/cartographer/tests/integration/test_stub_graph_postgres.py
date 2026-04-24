"""Integration: Postgres checkpointer (Docker) — fresh run and checkpoint list."""

from __future__ import annotations

import uuid

import pytest
from deployai_checkpointer import async_postgres_saver, checkpointer_thread_id
from testcontainers.postgres import PostgresContainer

from cartographer.stub_graph import build_stub_graph, canned_envelopes

pytestmark = pytest.mark.integration


def _pg_url(raw: str) -> str:
    """``AsyncPostgresSaver`` expects a plain ``postgresql://`` DSN (psycopg3 parses it)."""
    u = raw.replace("postgresql+psycopg2", "postgresql")
    u = u.replace("postgresql+psycopg", "postgresql")
    return u


@pytest.mark.asyncio
async def test_postgres_checkpoint_fresh_run() -> None:
    from docker.errors import DockerException  # type: ignore[import-untyped]

    try:
        c = PostgresContainer("postgres:16-alpine")
        c.start()
    except (DockerException, OSError, Exception):
        pytest.skip("Docker not available for Postgres testcontainer")

    try:
        url = _pg_url(c.get_connection_url())
        async with async_postgres_saver(url) as saver:
            app = build_stub_graph().compile(checkpointer=saver)
            tid = uuid.uuid4()
            cfg = {
                "configurable": {
                    "thread_id": checkpointer_thread_id(tenant_id=tid, run_key="it-1"),
                }
            }
            out = await app.ainvoke({"step": 0, "envelopes": []}, cfg)
        assert out["envelopes"] == [e.model_dump(mode="json") for e in canned_envelopes()]

        async with async_postgres_saver(url) as saver2:
            cps = [x async for x in saver2.alist({"configurable": cfg["configurable"]})]
        assert len(cps) >= 1
    finally:
        c.stop()
