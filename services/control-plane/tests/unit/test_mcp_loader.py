"""Unit tests for Wave 3G's :mod:`mcp_loader` module.

No Postgres / network. The :class:`McpOutboundClient` is replaced with a
``_StubClient`` that records every ``list_tools`` call so the tests can
assert ordering + filtering without spinning up a real outbound client.

Covers:

1. Namespace helpers (``namespace_tool_name``,
   ``split_external_tool_name``, ``is_external_tool_name``).
2. :func:`load_enabled_mcp_tools` returns one entry per enabled config
   with the upstream tool list.
3. Failed discovery (``list_tools`` raises a typed McpOutboundError) is
   silently omitted — the rest of the turn continues.
4. ``allowed_tools`` filter applied; ``None`` means "any tool"; an
   explicit empty list means "nothing".
5. :func:`external_tools_to_anthropic_specs` produces the expected
   Anthropic shape with namespaced names.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from control_plane.agents.agent_kenny.mcp_loader import (
    EXTERNAL_TOOL_NAMESPACE_SEPARATOR,
    LoadedMcpTools,
    external_tools_to_anthropic_specs,
    find_loaded_config,
    is_external_tool_name,
    load_enabled_mcp_tools,
    namespace_tool_name,
    split_external_tool_name,
)
from control_plane.agents.agent_kenny.mcp_types import (
    McpProtocolError,
    McpToolSpec,
    McpTransportError,
)
from control_plane.domain.mcp_outbound import CONNECTOR_KINDS

# --------------------------------------------------------------------------
# Stubs
# --------------------------------------------------------------------------


@dataclass
class _FakeConfig:
    """Stand-in for :class:`TenantMcpConfig` — only the attributes the
    loader reads.
    """

    id: uuid.UUID = field(default_factory=uuid.uuid4)
    tenant_id: uuid.UUID = field(default_factory=uuid.uuid4)
    name: str = "slack-prod"
    connector_kind: str = "slack"
    endpoint: str = "https://mcp.example.com/rpc"
    encrypted_auth_token: bytes | None = b"\x00\x01"
    allowed_tools: list[str] | None = None
    enabled: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _StubClient:
    """Records list_tools calls; returns a per-connector-kind tool list."""

    def __init__(self, by_kind: dict[str, list[McpToolSpec]] | None = None) -> None:
        self._by_kind = by_kind or {}
        self._raises_for: set[uuid.UUID] = set()
        self.calls: list[uuid.UUID] = []

    def will_raise_for(self, config_id: uuid.UUID, exc: Exception) -> None:
        self._raises_for.add(config_id)
        self._exc_for: dict[uuid.UUID, Exception] = getattr(self, "_exc_for", {})
        self._exc_for[config_id] = exc

    async def list_tools(self, config: Any) -> list[McpToolSpec]:
        self.calls.append(config.id)
        if config.id in self._raises_for:
            raise self._exc_for[config.id]
        return list(self._by_kind.get(config.connector_kind, []))


class _StubSession:
    """Wraps a pre-filled list of TenantMcpConfig rows for ``session.execute``.

    The loader runs::

        (await session.execute(stmt)).scalars().all()

    so we only need ``execute`` → ``scalars`` → ``all`` to walk the list.
    """

    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows
        self.last_stmt: Any = None

    async def execute(self, stmt: Any) -> Any:
        self.last_stmt = stmt
        rows = self._rows

        class _Result:
            def scalars(self_inner) -> Any:  # noqa: N805 — inner helper class, no real `self`
                class _Scalars:
                    def all(_inner) -> list[Any]:  # noqa: N805 — inner helper class
                        return list(rows)

                return _Scalars()

        return _Result()


# --------------------------------------------------------------------------
# 1. Namespace helpers
# --------------------------------------------------------------------------


def test_namespace_separator_is_double_underscore() -> None:
    # Anthropic API restricts tool names to ``^[a-zA-Z0-9_-]{1,128}$`` so
    # ``.`` would 400; the loader documents the ``__`` choice in its module
    # docstring. Asserting on the constant pins that decision.
    assert EXTERNAL_TOOL_NAMESPACE_SEPARATOR == "__"


def test_namespace_tool_name_builds_prefixed_form() -> None:
    assert namespace_tool_name("slack", "search_messages") == "slack__search_messages"
    assert namespace_tool_name("linear", "list_issues") == "linear__list_issues"


def test_split_external_tool_name_round_trips() -> None:
    for kind in CONNECTOR_KINDS:
        name = namespace_tool_name(kind, "do_thing")
        parts = split_external_tool_name(name)
        assert parts == (kind, "do_thing")


def test_split_external_tool_name_returns_none_for_internal() -> None:
    assert split_external_tool_name("query_ledger") is None
    assert split_external_tool_name("get_engagement_summary") is None
    # An internal tool that happens to contain "__" must not falsely
    # match — the connector-kind prefix has to be an exact catalog entry.
    assert split_external_tool_name("slack_things__foo") is None


def test_is_external_tool_name_for_every_connector_kind() -> None:
    for kind in CONNECTOR_KINDS:
        assert is_external_tool_name(f"{kind}__anything") is True
    assert is_external_tool_name("query_ledger") is False
    assert is_external_tool_name("slack_things__foo") is False


# --------------------------------------------------------------------------
# 2. load_enabled_mcp_tools — happy path
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_load_enabled_returns_one_entry_per_config_with_tools() -> None:
    tenant = uuid.uuid4()
    slack_cfg = _FakeConfig(tenant_id=tenant, connector_kind="slack", name="slack-prod")
    linear_cfg = _FakeConfig(tenant_id=tenant, connector_kind="linear", name="linear-prod")
    session = _StubSession([slack_cfg, linear_cfg])
    client = _StubClient(
        by_kind={
            "slack": [
                McpToolSpec(name="search_messages", description="search", input_schema={"type": "object"}),
                McpToolSpec(name="list_channels", description="channels", input_schema={"type": "object"}),
            ],
            "linear": [
                McpToolSpec(name="list_issues", description="issues", input_schema={"type": "object"}),
            ],
        },
    )

    loaded = await load_enabled_mcp_tools(session, tenant_id=tenant, client=client)

    assert len(loaded) == 2
    assert {entry.config.connector_kind for entry in loaded} == {"slack", "linear"}
    slack_entry = next(e for e in loaded if e.config.connector_kind == "slack")
    assert [t.name for t in slack_entry.tools] == ["search_messages", "list_channels"]
    linear_entry = next(e for e in loaded if e.config.connector_kind == "linear")
    assert [t.name for t in linear_entry.tools] == ["list_issues"]
    # Every config had its list_tools called exactly once.
    assert sorted(client.calls) == sorted([slack_cfg.id, linear_cfg.id])


# --------------------------------------------------------------------------
# 3. Discovery failure is degraded, not fatal
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_discovery_omits_config_from_merge() -> None:
    tenant = uuid.uuid4()
    failing = _FakeConfig(tenant_id=tenant, connector_kind="slack", name="slack-broken")
    ok = _FakeConfig(tenant_id=tenant, connector_kind="linear", name="linear-ok")
    session = _StubSession([failing, ok])
    client = _StubClient(
        by_kind={
            "linear": [McpToolSpec(name="list_issues", description="d", input_schema={"type": "object"})],
        },
    )
    client.will_raise_for(failing.id, McpTransportError("upstream 503"))

    loaded = await load_enabled_mcp_tools(session, tenant_id=tenant, client=client)

    # Failing config dropped; OK config still present.
    assert len(loaded) == 1
    assert loaded[0].config.connector_kind == "linear"
    assert loaded[0].tools[0].name == "list_issues"
    # Both configs were attempted (so the audit trail captures the failure
    # via mcp_client's own audit emit; the loader doesn't double-audit).
    assert sorted(client.calls) == sorted([failing.id, ok.id])


@pytest.mark.asyncio
async def test_failed_discovery_with_protocol_error_omits_config() -> None:
    tenant = uuid.uuid4()
    broken = _FakeConfig(tenant_id=tenant, connector_kind="github", name="github-broken")
    session = _StubSession([broken])
    client = _StubClient()
    client.will_raise_for(broken.id, McpProtocolError("malformed envelope"))

    loaded = await load_enabled_mcp_tools(session, tenant_id=tenant, client=client)

    assert loaded == []


@pytest.mark.asyncio
async def test_unexpected_exception_in_discovery_is_swallowed() -> None:
    """Belt-and-suspenders: a non-typed exception in list_tools must not
    crash the turn — the loader logs + drops the config.
    """
    tenant = uuid.uuid4()
    weird = _FakeConfig(tenant_id=tenant, connector_kind="notion", name="notion-weird")
    session = _StubSession([weird])
    client = _StubClient()
    client.will_raise_for(weird.id, RuntimeError("totally unexpected"))

    loaded = await load_enabled_mcp_tools(session, tenant_id=tenant, client=client)

    assert loaded == []


# --------------------------------------------------------------------------
# 4. allowed_tools filter
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_allowed_tools_none_permits_every_advertised_tool() -> None:
    tenant = uuid.uuid4()
    cfg = _FakeConfig(tenant_id=tenant, connector_kind="slack", allowed_tools=None)
    session = _StubSession([cfg])
    client = _StubClient(
        by_kind={
            "slack": [
                McpToolSpec(name="search_messages", description="d", input_schema={"type": "object"}),
                McpToolSpec(name="post_message", description="d", input_schema={"type": "object"}),
                McpToolSpec(name="list_channels", description="d", input_schema={"type": "object"}),
            ],
        },
    )

    loaded = await load_enabled_mcp_tools(session, tenant_id=tenant, client=client)

    assert {t.name for t in loaded[0].tools} == {"search_messages", "post_message", "list_channels"}


@pytest.mark.asyncio
async def test_allowed_tools_filter_restricts_to_named_subset() -> None:
    tenant = uuid.uuid4()
    cfg = _FakeConfig(
        tenant_id=tenant,
        connector_kind="slack",
        allowed_tools=["search_messages", "list_channels"],
    )
    session = _StubSession([cfg])
    client = _StubClient(
        by_kind={
            "slack": [
                McpToolSpec(name="search_messages", description="d", input_schema={"type": "object"}),
                McpToolSpec(name="post_message", description="d", input_schema={"type": "object"}),
                McpToolSpec(name="list_channels", description="d", input_schema={"type": "object"}),
            ],
        },
    )

    loaded = await load_enabled_mcp_tools(session, tenant_id=tenant, client=client)

    # ``post_message`` not in allow-list → dropped before the LLM ever sees it.
    assert {t.name for t in loaded[0].tools} == {"search_messages", "list_channels"}


@pytest.mark.asyncio
async def test_allowed_tools_empty_list_means_nothing_allowed() -> None:
    """An admin who saves an empty allow-list as soft-disable gets exactly
    what they asked for — no tools available, not "everything allowed".
    """
    tenant = uuid.uuid4()
    cfg = _FakeConfig(tenant_id=tenant, connector_kind="slack", allowed_tools=[])
    session = _StubSession([cfg])
    client = _StubClient(
        by_kind={
            "slack": [
                McpToolSpec(name="search_messages", description="d", input_schema={"type": "object"}),
            ],
        },
    )

    loaded = await load_enabled_mcp_tools(session, tenant_id=tenant, client=client)

    assert loaded[0].tools == []


# --------------------------------------------------------------------------
# 5. external_tools_to_anthropic_specs translation
# --------------------------------------------------------------------------


def test_external_tools_to_anthropic_specs_uses_namespaced_names() -> None:
    cfg = _FakeConfig(connector_kind="slack")
    loaded = [
        LoadedMcpTools(
            config=cfg,
            tools=[
                McpToolSpec(
                    name="search_messages",
                    description="Search Slack messages.",
                    input_schema={"type": "object", "properties": {"q": {"type": "string"}}},
                ),
            ],
        )
    ]

    specs = external_tools_to_anthropic_specs(loaded)

    assert len(specs) == 1
    assert specs[0]["name"] == "slack__search_messages"
    assert specs[0]["description"] == "Search Slack messages."
    assert specs[0]["input_schema"]["type"] == "object"
    assert specs[0]["input_schema"]["properties"]["q"]["type"] == "string"


def test_external_tools_to_anthropic_specs_normalizes_empty_schema() -> None:
    cfg = _FakeConfig(connector_kind="github")
    loaded = [
        LoadedMcpTools(
            config=cfg,
            tools=[
                McpToolSpec(name="ping", description="No args.", input_schema={}),
                McpToolSpec(name="ping2", description="None.", input_schema={}),
            ],
        )
    ]

    specs = external_tools_to_anthropic_specs(loaded)

    assert all(spec["input_schema"] == {"type": "object"} for spec in specs)
    assert specs[0]["name"] == "github__ping"
    assert specs[1]["name"] == "github__ping2"


def test_find_loaded_config_returns_first_match_per_kind() -> None:
    slack_one = _FakeConfig(connector_kind="slack", name="slack-a")
    slack_two = _FakeConfig(connector_kind="slack", name="slack-b")
    loaded = [
        LoadedMcpTools(config=slack_one, tools=[]),
        LoadedMcpTools(config=slack_two, tools=[]),
    ]

    cfg = find_loaded_config(loaded, connector_kind="slack")

    assert cfg is slack_one


def test_find_loaded_config_returns_none_when_missing() -> None:
    loaded = [LoadedMcpTools(config=_FakeConfig(connector_kind="linear"), tools=[])]
    assert find_loaded_config(loaded, connector_kind="slack") is None
