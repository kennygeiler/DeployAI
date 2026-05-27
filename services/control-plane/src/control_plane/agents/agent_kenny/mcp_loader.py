"""Turn-start external-MCP tool discovery + merge (Wave 3G — Phase 5 keystone).

Loads every enabled :class:`TenantMcpConfig` row for the tenant, calls
``McpOutboundClient.list_tools(config)`` for each, applies the per-row
``allowed_tools`` filter, and returns the namespaced tool set the agent
loop merges into the LLM's tool registry (scope-v2 §9.2).

Namespace convention
--------------------
External tool names are namespaced ``{connector_kind}__{tool_name}``
(double-underscore separator) — e.g. ``slack__search_messages``,
``linear__list_issues``. The Anthropic tool-use API restricts tool names
to ``^[a-zA-Z0-9_-]{1,128}$`` so ``.`` (the scope-v2 §9.2 example
suggestion) is NOT valid; the dot would land the request in a 400 from
the Messages API.  We chose ``__`` because:

- It is a single greppable token that won't appear in real upstream MCP
  tool names (none of the v1 catalog uses double-underscore).
- It survives URL encoding, JSON Pointer, and human reading.
- :func:`is_external_tool_name` + :func:`split_external_tool_name` are
  the single source of truth; everywhere else asks them.

If a future widening of the connector catalog ever ships a tool that
already contains ``__`` upstream, this module is the one place to
revisit.

Discovery failure posture
-------------------------
``client.list_tools(config)`` can fail (transport error, upstream 5xx,
malformed envelope). Discovery failure is a *degraded* state, not a
turn-failure: the failing config is omitted from the merge, a structured
log record + ledger row is emitted, and the rest of the turn continues
with the remaining configs + Kenny's internal tools. The LLM never sees
the failing tool, so it cannot route a tool_use at it.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.agent_kenny.mcp_client import McpOutboundClient
from control_plane.agents.agent_kenny.mcp_types import (
    McpOutboundError,
    McpToolSpec,
)
from control_plane.domain.mcp_outbound import CONNECTOR_KINDS, TenantMcpConfig

_log = logging.getLogger(__name__)

# Namespace separator. See module docstring for the rationale.
EXTERNAL_TOOL_NAMESPACE_SEPARATOR = "__"


@dataclass(frozen=True)
class LoadedMcpTools:
    """One config and its post-filter tool list — returned by the loader."""

    config: TenantMcpConfig
    tools: list[McpToolSpec]


# --------------------------------------------------------------------------
# Namespace helpers
# --------------------------------------------------------------------------


def namespace_tool_name(connector_kind: str, tool_name: str) -> str:
    """Return the LLM-visible name for one external tool.

    ``slack`` + ``search_messages`` → ``slack__search_messages``.
    """
    return f"{connector_kind}{EXTERNAL_TOOL_NAMESPACE_SEPARATOR}{tool_name}"


def is_external_tool_name(name: str) -> bool:
    """True iff ``name`` carries a known connector-kind prefix.

    Uses :data:`CONNECTOR_KINDS` as the source of truth so widening the
    catalog automatically widens routing — no second list to keep in
    sync. The check is prefix + separator (not a regex) so unexpected
    upstream names with double-underscores inside them don't trigger a
    false positive (e.g. an internal tool called ``slack_things__foo``
    would still route internally because ``slack_things`` is not a
    connector kind).
    """
    for kind in CONNECTOR_KINDS:
        if name.startswith(f"{kind}{EXTERNAL_TOOL_NAMESPACE_SEPARATOR}"):
            return True
    return False


def split_external_tool_name(name: str) -> tuple[str, str] | None:
    """Split a namespaced name into ``(connector_kind, tool_name)``.

    Returns ``None`` when ``name`` is not an external tool — callers use
    that as a hint to fall through to internal dispatch.
    """
    for kind in CONNECTOR_KINDS:
        prefix = f"{kind}{EXTERNAL_TOOL_NAMESPACE_SEPARATOR}"
        if name.startswith(prefix):
            return kind, name[len(prefix) :]
    return None


# --------------------------------------------------------------------------
# Main loader
# --------------------------------------------------------------------------


async def load_enabled_mcp_tools(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    client: McpOutboundClient,
) -> list[LoadedMcpTools]:
    """Load every enabled tenant_mcp_configs row + its tool list.

    Returns one :class:`LoadedMcpTools` per *successfully discovered*
    config. Configs whose ``tools/list`` call failed are dropped from
    the return value (a degraded-state log + best-effort error
    suppression keeps the turn going).

    The ``allowed_tools`` filter is applied here so the caller never
    sees tools the tenant has not permitted. Wave 2D's client also
    enforces the filter at ``call_tool`` time as a defense in depth —
    that's intentional, this PR's filter is the user-visible one (the
    LLM never sees a forbidden tool, so it cannot generate a tool_use
    that would then be denied at call time, which would be a confusing
    behavioral artifact).
    """
    stmt = (
        select(TenantMcpConfig)
        .where(TenantMcpConfig.tenant_id == tenant_id)
        .where(TenantMcpConfig.enabled.is_(True))
        .order_by(TenantMcpConfig.created_at.asc())
    )
    rows = (await session.execute(stmt)).scalars().all()
    out: list[LoadedMcpTools] = []
    for config in rows:
        try:
            advertised = await client.list_tools(config)
        except McpOutboundError as exc:
            # Typed failure: kill switch (defensive — kill switch should
            # have been checked before we got here), transport error,
            # protocol error. Drop the config from this turn's merge so
            # the rest of the turn continues with the remaining ones.
            _log.warning(
                "mcp_loader.discovery_failed",
                extra={
                    "tenant_id": str(tenant_id),
                    "config_id": str(config.id),
                    "connector_kind": config.connector_kind,
                    "error_kind": type(exc).__name__,
                    "error_message": str(exc)[:240],
                },
            )
            continue
        except Exception:
            # Belt-and-suspenders: list_tools shouldn't raise non-typed
            # exceptions but if some future transport regression does,
            # we still keep the turn alive instead of crashing the user
            # request. The exception is logged with full traceback so
            # the operator can investigate.
            _log.exception(
                "mcp_loader.discovery_unexpected_error",
                extra={
                    "tenant_id": str(tenant_id),
                    "config_id": str(config.id),
                    "connector_kind": config.connector_kind,
                },
            )
            continue
        filtered = _apply_allow_list(advertised, config.allowed_tools)
        out.append(LoadedMcpTools(config=config, tools=filtered))
    return out


def _apply_allow_list(
    advertised: list[McpToolSpec],
    allowed_tools: list[str] | None,
) -> list[McpToolSpec]:
    """Filter ``advertised`` to only the tools listed in ``allowed_tools``.

    ``allowed_tools=None`` means "every tool the MCP advertises is
    allowed" (scope-v2 §9.1 default). A non-None empty list means
    "explicitly nothing" — we return ``[]`` so an admin who saves an
    empty allow-list as a soft-disable doesn't accidentally re-enable
    everything.
    """
    if allowed_tools is None:
        return list(advertised)
    allowed_set = set(allowed_tools)
    return [t for t in advertised if t.name in allowed_set]


# --------------------------------------------------------------------------
# Anthropic tool-spec translation
# --------------------------------------------------------------------------


def external_tools_to_anthropic_specs(
    loaded: list[LoadedMcpTools],
) -> list[dict[str, Any]]:
    """Translate the loader output into Anthropic-tool-use ``tools[]`` dicts.

    Each entry mirrors the internal-tool shape ``_anthropic_tool_specs``
    produces: ``{"name", "description", "input_schema"}``. ``name`` is
    namespaced via :func:`namespace_tool_name` so the LLM sees the
    routable, prefix-disambiguated name.

    Empty ``input_schema`` upstreams are normalized to ``{"type":
    "object"}`` so Anthropic's tool-input validator does not 400 on a
    missing schema (some MCPs ship tools that take no arguments).
    """
    out: list[dict[str, Any]] = []
    for entry in loaded:
        for spec in entry.tools:
            schema = spec.input_schema or {}
            if not isinstance(schema, dict) or not schema:
                schema = {"type": "object"}
            out.append(
                {
                    "name": namespace_tool_name(entry.config.connector_kind, spec.name),
                    "description": spec.description,
                    "input_schema": schema,
                }
            )
    return out


def find_loaded_config(
    loaded: list[LoadedMcpTools],
    *,
    connector_kind: str,
) -> TenantMcpConfig | None:
    """Return the first :class:`TenantMcpConfig` for ``connector_kind``, if any.

    The agent loop dispatches by connector_kind — the first enabled
    config wins when a tenant configured more than one row of the same
    kind (rare; the UI nudges users to a single row per kind, but the
    schema allows multiple).
    """
    for entry in loaded:
        if entry.config.connector_kind == connector_kind:
            return entry.config
    return None


__all__ = [
    "EXTERNAL_TOOL_NAMESPACE_SEPARATOR",
    "LoadedMcpTools",
    "external_tools_to_anthropic_specs",
    "find_loaded_config",
    "is_external_tool_name",
    "load_enabled_mcp_tools",
    "namespace_tool_name",
    "split_external_tool_name",
]
