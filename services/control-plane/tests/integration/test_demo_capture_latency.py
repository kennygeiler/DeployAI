"""Wave 3 K4 — the demo's capture loop, timed, on the real demo artifacts.

The cold-start demo lives or dies on artifact→proposals turnaround (<30s
budget, K2). This suite drives the exact server loop the Capture tab uses —
``POST /ingest`` (staged, no chained extraction) then ``POST /extract`` —
over the three staged files in ``demo/artifacts/`` and prints a per-stage
latency table (run with ``-s`` to see it on success).

Honesty note on the numbers: the LLM here is a deterministic stub, so the
measured extract time is the *platform overhead* (routing, tenant scoping,
event load, proposal persistence, ledger emit, webhooks) — the floor under
any real run. The live-LLM latency on these artifacts is verified against
the compose stack (see the demo runbook, K5); the UI side of the async
window is pinned in apps/web .../CaptureIngest.test.tsx, which holds the
"Extracting…" state across deferred /ingest + /extract promises exactly as
the polling logic must.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import CapabilityMatrix, ChatMessage
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.llm import get_llm_provider
from control_plane.api.routes.demo_reset_internal import ACME_ENGAGEMENT_ID
from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration

TENANT_ID = uuid.UUID("11111111-1111-4111-8111-bbbbbbbbbbbb")

REPO_ROOT = Path(__file__).resolve().parents[4]
ARTIFACTS_DIR = REPO_ROOT / "demo" / "artifacts"

# Per-artifact stub extractor output — shaped like real Cartographer JSON,
# echoing what each artifact is scripted to yield in the live demo.
ARTIFACT_CASES: tuple[tuple[str, str, list[dict[str, object]]], ...] = (
    (
        "kickoff-transcript.txt",
        "meeting_note",
        [
            {
                "kind": "node",
                "node_type": "decision",
                "title": "Edge inference on-robot for the pilot",
                "rationale": "Dana Ruiz called it in the kickoff after the latency-budget discussion.",
            },
            {
                "kind": "node",
                "node_type": "stakeholder",
                "title": "Dana Ruiz (CTO, Acme Robotics)",
                "rationale": "Owns board comms and the WMS vendor relationship.",
            },
            {
                "kind": "node",
                "node_type": "stakeholder",
                "title": "Marcus Webb (Head of Operations)",
                "rationale": "Owns safety certification and associate training.",
            },
        ],
    ),
    (
        "email-thread.txt",
        "email",
        [
            {
                "kind": "node",
                "node_type": "commitment",
                "title": "Safety-cert documentation package delivered by October 3",
                "rationale": "Marcus Webb committed mid-thread on Sep 22.",
            },
        ],
    ),
    (
        "slack-export.txt",
        "manual_import",
        [
            {
                "kind": "node",
                "node_type": "risk",
                "title": "Warehouse wifi dead zones may break the fleet heartbeat",
                "rationale": "Tom Okafor saw 3-4s packet loss between rows E and F; halting is the safety default.",
            },
        ],
    ),
)

# Platform-overhead ceiling per stage with the stub LLM. Generous on purpose
# (CI containers are slow); the point is to fail if the loop ever gains an
# accidental N+1 or sync sleep, not to benchmark the LLM.
STAGE_BUDGET_SECONDS = 5.0


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


class _FakeLLM:
    id = "fake"

    def __init__(self) -> None:
        self.response = "[]"
        self.calls = 0

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = messages, temperature, max_output_tokens
        self.calls += 1
        return self.response

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = temperature, max_output_tokens
        yield self.chat_complete(messages)

    def embed(self, text: str) -> list[float]:
        return pseudo_embed(text, 16)

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


@pytest_asyncio.fixture
async def client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "capture-latency-test-key")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    c = AsyncClient(transport=transport, base_url="http://test")
    c.headers["X-DeployAI-Internal-Key"] = "capture-latency-test-key"
    try:
        yield c
    finally:
        await c.aclose()
        clear_engine_cache()


@pytest.fixture
def fake_llm() -> Iterator[_FakeLLM]:
    fake = _FakeLLM()
    app.dependency_overrides[get_llm_provider] = lambda: fake
    try:
        yield fake
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'capture-latency') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


@pytest.mark.asyncio
async def test_demo_artifacts_ingest_extract_proposals_loop(
    client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    """The exact staged loop the Capture tab drives, over all three artifacts."""
    _ins_tenant(postgres_engine, TENANT_ID)
    r = await client.post(f"/internal/v1/admin/demo/reset-acme?tenant_id={TENANT_ID}")
    assert r.status_code == 200, r.text

    rows: list[tuple[str, float, float, int]] = []
    for filename, source, stub_proposals in ARTIFACT_CASES:
        artifact = ARTIFACTS_DIR / filename
        assert artifact.exists(), f"staged demo artifact missing: {artifact}"
        body_text = artifact.read_text()
        assert len(body_text.splitlines()) >= 20, f"{filename} is too thin to demo with"

        fake_llm.response = json.dumps(stub_proposals)

        t0 = time.monotonic()
        ingest = await client.post(
            f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}/ingest?tenant_id={TENANT_ID}",
            json={
                "source": source,
                "occurred_at": "2026-10-01T17:00:00Z",
                "content": {"text": body_text},
                "source_ref": f"demo/artifacts/{filename}",
            },
        )
        t_ingest = time.monotonic() - t0
        assert ingest.status_code == 201, ingest.text
        event_id = ingest.json()["id"]

        t1 = time.monotonic()
        extract = await client.post(
            f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}/extract?tenant_id={TENANT_ID}&event_id={event_id}"
        )
        t_extract = time.monotonic() - t1
        assert extract.status_code == 201, extract.text
        proposals = extract.json()

        # The demo's core promise: every staged artifact yields proposals.
        assert len(proposals) == len(stub_proposals), filename
        assert all(p["status"] == "pending" for p in proposals), filename
        assert all(p["source_event_id"] == event_id for p in proposals), filename

        assert t_ingest < STAGE_BUDGET_SECONDS, f"{filename}: ingest overhead {t_ingest:.2f}s"
        assert t_extract < STAGE_BUDGET_SECONDS, f"{filename}: extract overhead {t_extract:.2f}s"
        rows.append((filename, t_ingest, t_extract, len(proposals)))

    print("\nK4 capture-loop latency (stub LLM = platform overhead floor):")
    print(f"  {'artifact':<26} {'ingest':>9} {'extract':>9} {'proposals':>10}")
    for filename, t_ingest, t_extract, n in rows:
        print(f"  {filename:<26} {t_ingest * 1000:>7.0f}ms {t_extract * 1000:>7.0f}ms {n:>10}")
    total = sum(t_i + t_e for _, t_i, t_e, _ in rows)
    print(
        f"  total platform overhead for all 3 artifacts: {total * 1000:.0f}ms "
        "(demo budget: <30s per artifact with live LLM)"
    )


@pytest.mark.asyncio
async def test_extract_is_idempotent_across_ui_refreshes(
    client: AsyncClient, postgres_engine: Engine, fake_llm: _FakeLLM
) -> None:
    """The async window's safety net: re-running extract (a retry, a refresh
    race, a double click) returns the same proposals without a second LLM
    call — so the UI's poll/refresh after 'Extracting…' can never duplicate
    proposals."""
    _ins_tenant(postgres_engine, TENANT_ID)
    r = await client.post(f"/internal/v1/admin/demo/reset-acme?tenant_id={TENANT_ID}")
    assert r.status_code == 200, r.text

    fake_llm.response = json.dumps(ARTIFACT_CASES[1][2])
    ingest = await client.post(
        f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}/ingest?tenant_id={TENANT_ID}",
        json={
            "source": "email",
            "occurred_at": "2026-09-22T23:47:00Z",
            "content": {"text": (ARTIFACTS_DIR / "email-thread.txt").read_text()},
        },
    )
    assert ingest.status_code == 201, ingest.text
    event_id = ingest.json()["id"]

    first = await client.post(
        f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}/extract?tenant_id={TENANT_ID}&event_id={event_id}"
    )
    assert first.status_code == 201, first.text
    assert fake_llm.calls == 1

    second = await client.post(
        f"/internal/v1/engagements/{ACME_ENGAGEMENT_ID}/extract?tenant_id={TENANT_ID}&event_id={event_id}"
    )
    assert second.status_code == 201, second.text
    assert fake_llm.calls == 1, "idempotent re-extract must not re-call the LLM"
    assert [p["id"] for p in second.json()] == [p["id"] for p in first.json()]
