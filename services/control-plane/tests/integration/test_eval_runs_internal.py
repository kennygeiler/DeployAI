"""Integration: eval-run history routes (Wave 4 showcase, ticket G8).

``POST /internal/v1/admin/eval-runs`` accepts the golden eval runner's
report JSON and lifts the summary fields into typed columns; ``GET`` lists
runs newest-first for the admin dashboard's trend view. Coverage:

- runner-shaped report → 201 with the runner's field names mapped
  (``total_questions`` → ``question_count``, ``latency_p50_ms`` →
  ``p50_ms``) and the WHOLE payload stored verbatim in ``report`` jsonb;
- liberal ingest: an empty body still records a run (zero defaults,
  ``source`` from the query param, defaulting to ``local``);
- unknown ``source`` → 422; missing internal key → 401;
- GET orders newest-first and respects ``limit``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration

_GLOBAL_KEY = "eval-runs-test-global-key"


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


@pytest_asyncio.fixture
async def client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", _GLOBAL_KEY)
    clear_engine_cache()
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://test")
    c.headers["X-DeployAI-Internal-Key"] = _GLOBAL_KEY
    try:
        yield c
    finally:
        await c.aclose()
        clear_engine_cache()


def _runner_report(**overrides: Any) -> dict[str, Any]:
    """A report shaped like tests/golden/agent_kenny/runner.py writes it."""
    report: dict[str, Any] = {
        "started_at": "2026-08-11T10:00:00Z",
        "finished_at": "2026-08-11T10:12:00Z",
        "total_questions": 30,
        "pass_rate": 0.9,
        "idk_rate": 0.2,
        "hallucination_rate": 0.03,
        "cross_engagement_leak_count": 0,
        "latency_p50_ms": 1200,
        "latency_p95_ms": 4100,
        "latency_p99_ms": 6800,
        "runtime": "langgraph",
        "by_category": [],
        "results": [{"id": "dl-01", "category": "direct_lookup", "expected_pass": True}],
    }
    report.update(overrides)
    return report


@pytest.mark.asyncio
async def test_record_run_maps_runner_fields_and_stores_whole_report(
    postgres_engine: Engine, client: AsyncClient
) -> None:
    resp = await client.post("/internal/v1/admin/eval-runs?source=ci", json=_runner_report())
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "ci"
    assert body["runtime"] == "langgraph"
    assert body["question_count"] == 30
    assert body["pass_rate"] == 0.9
    assert body["idk_rate"] == 0.2
    assert body["hallucination_rate"] == 0.03
    assert body["cross_engagement_leak_count"] == 0
    assert body["p50_ms"] == 1200.0
    assert body["p95_ms"] == 4100.0
    assert body["run_at"]

    # The whole payload (including per-question results) is kept verbatim.
    with postgres_engine.connect() as conn:
        stored = conn.execute(text("SELECT report FROM eval_runs WHERE id = :i"), {"i": body["id"]}).scalar_one()
    assert stored == _runner_report()


@pytest.mark.asyncio
async def test_record_run_is_liberal_about_missing_fields(client: AsyncClient) -> None:
    # An empty report still records a run: zero defaults, source defaults
    # to "local", latency percentiles stay null (unknown, not zero).
    resp = await client.post("/internal/v1/admin/eval-runs", json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "local"
    assert body["runtime"] is None
    assert body["question_count"] == 0
    assert body["pass_rate"] == 0.0
    assert body["cross_engagement_leak_count"] == 0
    assert body["p50_ms"] is None
    assert body["p95_ms"] is None

    # Storage-name variants are accepted too, and a source inside the
    # report wins over the query param.
    resp = await client.post(
        "/internal/v1/admin/eval-runs?source=ci",
        json={"source": "longitudinal", "question_count": 5, "p50_ms": 900.5},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["source"] == "longitudinal"
    assert body["question_count"] == 5
    assert body["p50_ms"] == 900.5


@pytest.mark.asyncio
async def test_record_run_rejects_unknown_source_and_missing_key(client: AsyncClient) -> None:
    resp = await client.post("/internal/v1/admin/eval-runs?source=prod", json={})
    assert resp.status_code == 422, resp.text

    resp = await client.post(
        "/internal/v1/admin/eval-runs",
        json=_runner_report(),
        headers={"X-DeployAI-Internal-Key": "wrong-key"},
    )
    assert resp.status_code == 401

    resp = await client.get("/internal/v1/admin/eval-runs", headers={"X-DeployAI-Internal-Key": ""})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_runs_newest_first_with_limit(postgres_engine: Engine, client: AsyncClient) -> None:
    # Seed three runs with distinct run_at values (POST uses now(), so
    # insert directly to control ordering).
    with postgres_engine.begin() as conn:
        for i, (day, rate) in enumerate([(1, 0.5), (2, 0.7), (3, 0.9)]):
            conn.execute(
                text(
                    "INSERT INTO eval_runs "
                    "(run_at, source, question_count, pass_rate, idk_rate, hallucination_rate, "
                    " cross_engagement_leak_count, report) "
                    f"VALUES ('2026-08-0{day}T00:00:00Z', 'ci', 30, :r, 0.1, 0.01, :i, '{{}}'::jsonb)"
                ),
                {"r": rate, "i": i},
            )

    resp = await client.get("/internal/v1/admin/eval-runs")
    assert resp.status_code == 200, resp.text
    runs = resp.json()["runs"]
    assert [r["pass_rate"] for r in runs] == [0.9, 0.7, 0.5]
    # The list payload is the typed summary only — no raw report blob.
    assert "report" not in runs[0]

    resp = await client.get("/internal/v1/admin/eval-runs?limit=2")
    assert resp.status_code == 200
    assert [r["pass_rate"] for r in resp.json()["runs"]] == [0.9, 0.7]

    resp = await client.get("/internal/v1/admin/eval-runs?limit=0")
    assert resp.status_code == 422
