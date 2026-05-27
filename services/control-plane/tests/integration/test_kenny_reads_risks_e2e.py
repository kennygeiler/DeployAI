"""E2E: Kenny can answer "what are the risks?" off raw matrix_nodes.

Regression for the load-bearing bug where ``get_open_risks`` only queried
``matrix_insights``; on a cold engagement with no synthesis layer yet,
Kenny reported "13 risks identified, cannot access details" because the
node-only data path returned 0 rows. After the
``analysis.get_open_risks`` union + new ``list_matrix_nodes_by_type``
tool, the LLM gets actual risk titles back and can paraphrase them.

The test drives Kenny via the same stub-LLM scaffolding the rest of the
v2 integration suite uses (see ``test_agent_kenny_v2``), seeds three
``risk``-typed matrix_nodes (no insights), scripts a single tool call to
``get_open_risks``, and verifies:

  1. The tool_result content surfaced through SSE actually contains the
     risk node titles (not just "3 risks identified" or similar).
  2. The final reply (paraphrased by the scripted LLM) mentions at least
     one of the seeded risk titles verbatim.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from llm_provider_py.types import (
    CapabilityMatrix,
    ChatMessage,
    StopReason,
    StreamChunk,
    TextDelta,
    ToolStreamChunk,
    ToolUseEnd,
    ToolUseStart,
)
from llm_provider_py.util import DEFAULT_CAPS, pseudo_embed
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.agents.llm import get_llm_provider
from control_plane.db import clear_engine_cache
from control_plane.main import app

pytestmark = pytest.mark.integration


_TOOL_CALL_SCRIPT_RE = re.compile(r"<tool_call>(.*?)</tool_call>", re.DOTALL)


def _split_reply_for_tool_use(reply: str) -> tuple[str, list[dict[str, Any]]]:
    blocks: list[dict[str, Any]] = []
    for idx, m in enumerate(_TOOL_CALL_SCRIPT_RE.finditer(reply)):
        body = m.group(1).strip()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        name = payload.get("name")
        if not isinstance(name, str):
            continue
        input_obj = payload.get("input", {})
        if not isinstance(input_obj, dict):
            input_obj = {}
        blocks.append({"id": f"toolu_script_{idx}", "name": name, "input": input_obj})
    text_remaining = _TOOL_CALL_SCRIPT_RE.sub("", reply).strip()
    return text_remaining, blocks


class _RiskReadingLLMScript:
    """Stub provider scripted for the risk-reading e2e.

    On call #1 it emits a ``tool_use`` for ``get_open_risks``. On call #2
    it inspects the prior ``user``-role messages (where tool_dispatch
    persisted the ``<tool_result>`` text) and paraphrases the first risk
    title it finds. This mirrors what a real model would do, but
    deterministically — the test is asserting plumbing, not LLM quality.
    """

    id = "stub-kenny-risk-reading"

    def __init__(self) -> None:
        self.calls = 0
        self.last_messages: list[ChatMessage] | None = None
        self.last_tool_result_text: str = ""
        self.last_final_reply: str = ""

    def chat_complete(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> str:
        _ = temperature, max_output_tokens
        self.last_messages = messages
        return "NONE"

    async def chat_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> AsyncIterator[str]:
        _ = messages, temperature, max_output_tokens
        yield ""

    async def chat_complete_stream(
        self,
        messages: list[ChatMessage],
        *,
        temperature: float = 0.2,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[StreamChunk]:
        _ = temperature, max_output_tokens
        self.last_messages = messages
        yield StreamChunk(delta="", done=True, tokens_used=120)

    async def chat_complete_stream_with_tools(
        self,
        messages: list[ChatMessage],
        tools: list[dict[str, Any]],
        *,
        temperature: float = 0.0,
        max_output_tokens: int = 1024,
    ) -> AsyncIterator[ToolStreamChunk]:
        _ = tools, temperature, max_output_tokens
        self.last_messages = messages
        idx = self.calls
        self.calls += 1

        if idx == 0:
            # Turn 1: ask for the open risks.
            reply = '<tool_call>{"name": "get_open_risks", "input": {}}</tool_call>'
            text_val, tool_blocks = _split_reply_for_tool_use(reply)
            if text_val:
                yield TextDelta(content=text_val)
            for block in tool_blocks:
                yield ToolUseStart(id=block["id"], name=block["name"])
                yield ToolUseEnd(id=block["id"], name=block["name"], input=block["input"])
            yield StopReason(reason="tool_use", usage={"input_tokens": 80, "output_tokens": 40})
            return

        # Turn 2: paraphrase the tool result. tool_dispatch appended a
        # ``<tool_result name="get_open_risks">{json-payload}</tool_result>``
        # user-role message; we scan the messages list for the first title
        # field in that JSON. (In a real run the LLM does this; here we
        # do it explicitly so the test asserts the data made it through.)
        title = self._first_risk_title_in_messages(messages)
        self.last_final_reply = (
            f"Top risk: {title}. Pulled from the engagement matrix." if title else "No risks visible."
        )
        yield TextDelta(content=self.last_final_reply)
        yield StopReason(reason="end_turn", usage={"input_tokens": 90, "output_tokens": 30})

    def _first_risk_title_in_messages(self, messages: list[ChatMessage]) -> str | None:
        """Scan messages for the first ``title`` inside a tool_result body."""
        for msg in reversed(messages):
            content = msg.get("content")
            text_blocks: list[str] = []
            if isinstance(content, str):
                text_blocks.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict):
                        if block.get("type") == "tool_result":
                            body = block.get("content")
                            if isinstance(body, str):
                                text_blocks.append(body)
                            elif isinstance(body, list):
                                for sub in body:
                                    if isinstance(sub, dict) and isinstance(sub.get("text"), str):
                                        text_blocks.append(sub["text"])
                        elif isinstance(block.get("text"), str):
                            text_blocks.append(block["text"])
            for chunk in text_blocks:
                if "get_open_risks" not in chunk and '"title"' not in chunk:
                    continue
                self.last_tool_result_text = chunk
                # Extract first ``"title": "..."``.
                m = re.search(r'"title"\s*:\s*"([^"]+)"', chunk)
                if m:
                    return m.group(1)
        return None

    def embed(self, text: str) -> list[float]:
        return list(pseudo_embed(text, 16))

    def capabilities(self) -> CapabilityMatrix:
        return {**DEFAULT_CAPS}


def _async_url(postgres_engine: Engine) -> str:
    return postgres_engine.url.set(drivername="postgresql+psycopg").render_as_string(hide_password=False)


def _ins_tenant(engine: Engine, tid: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'kenny-risks-e2e') ON CONFLICT (id) DO NOTHING"),
            {"t": str(tid)},
        )


def _ins_user(engine: Engine, tenant_id: uuid.UUID, user_id: uuid.UUID) -> None:
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO app_users (id, tenant_id, user_name, email) "
                "VALUES (:u, :t, :n, :e) ON CONFLICT (id) DO NOTHING"
            ),
            {
                "u": str(user_id),
                "t": str(tenant_id),
                "n": f"kenny-risks-{user_id}",
                "e": f"{user_id}@example.test",
            },
        )


def _ins_risk_node(
    engine: Engine,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    title: str,
    description: str,
) -> uuid.UUID:
    nid = uuid.uuid4()
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO matrix_nodes "
                "  (id, tenant_id, engagement_id, node_type, title, status, attributes, evidence_event_ids) "
                "VALUES (:i, :t, :e, 'risk', :ti, NULL, CAST(:a AS jsonb), '{}'::uuid[])"
            ),
            {
                "i": str(nid),
                "t": str(tenant_id),
                "e": str(engagement_id),
                "ti": title,
                "a": json.dumps({"description": description}),
            },
        )
    return nid


@pytest_asyncio.fixture
async def k_client(postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncClient]:
    monkeypatch.setenv("DATABASE_URL", _async_url(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_INTERNAL_API_KEY", "kenny-risks-e2e-key")
    monkeypatch.setenv("DEPLOYAI_AGENT_KENNY_V2_ENABLED", "1")
    clear_engine_cache()
    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")
    client.headers["X-DeployAI-Internal-Key"] = "kenny-risks-e2e-key"
    try:
        yield client
    finally:
        await client.aclose()
        clear_engine_cache()


@pytest.fixture
def stub_llm() -> Iterator[_RiskReadingLLMScript]:
    stub = _RiskReadingLLMScript()

    def _f() -> _RiskReadingLLMScript:
        return stub

    app.dependency_overrides[get_llm_provider] = _f
    try:
        yield stub
    finally:
        app.dependency_overrides.pop(get_llm_provider, None)


async def _new_engagement(client: AsyncClient, engine: Engine) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    tid = uuid.uuid4()
    _ins_tenant(engine, tid)
    user_id = uuid.uuid4()
    _ins_user(engine, tid, user_id)
    r = await client.post(f"/internal/v1/engagements?tenant_id={tid}", json={"name": "Kenny risks e2e"})
    assert r.status_code == 201, r.text
    return tid, uuid.UUID(r.json()["id"]), user_id


def _parse_sse_frames(payload: str) -> list[tuple[str, dict[str, Any]]]:
    frames: list[tuple[str, dict[str, Any]]] = []
    for block in payload.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        event_name = ""
        data_text = ""
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[len("event: ") :].strip()
            elif line.startswith("data: "):
                data_text = line[len("data: ") :].strip()
        if not event_name:
            continue
        try:
            frames.append((event_name, json.loads(data_text) if data_text else {}))
        except json.JSONDecodeError:
            continue
    return frames


@pytest.mark.asyncio
async def test_kenny_reads_risks_from_matrix_nodes_when_no_synthesis(
    k_client: AsyncClient, postgres_engine: Engine, stub_llm: _RiskReadingLLMScript
) -> None:
    """Three risk matrix_nodes seeded → tool returns titles → reply names one."""
    tid, eid, user_id = await _new_engagement(k_client, postgres_engine)

    risk_titles = [
        "Single point of failure in legacy auth service",
        "Vendor SLA reduces in Q3 ahead of cutover",
        "Stakeholder turnover on infra team",
    ]
    seeded_ids = [
        _ins_risk_node(
            postgres_engine,
            tenant_id=tid,
            engagement_id=eid,
            title=t,
            description=f"Detail body for {t}",
        )
        for t in risk_titles
    ]
    assert len(seeded_ids) == 3

    r = await k_client.post(
        f"/internal/v1/engagements/{eid}/oracle/chat/stream-v2?tenant_id={tid}",
        json={"conversation_id": None, "message": "high level what are the major risks"},
        headers={"X-DeployAI-Actor-Id": str(user_id)},
    )
    assert r.status_code == 200, r.text
    frames = _parse_sse_frames(r.text)
    events = [name for name, _ in frames]
    assert "tool_call" in events, frames
    assert "tool_result" in events, frames
    assert "done" in events, frames

    # The tool_result content the stub LLM saw must contain at least one
    # of the seeded risk titles — proves the data path actually flows
    # raw matrix_nodes through ``get_open_risks``.
    assert stub_llm.last_tool_result_text, "stub never observed a tool_result body"
    assert any(title in stub_llm.last_tool_result_text for title in risk_titles), (
        "tool_result body did not contain any of the seeded risk titles "
        f"(got: {stub_llm.last_tool_result_text[:400]!r})"
    )

    # The final reply must name at least one of the seeded titles.
    done_payload = next(p for name, p in frames if name == "done")
    final_text = str(done_payload.get("final_text") or "")
    assert any(t in final_text for t in risk_titles), (
        f"final reply did not mention any seeded risk title; reply was: {final_text!r}"
    )
