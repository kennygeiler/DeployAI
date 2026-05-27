"""v2 Phase 5 Wave 3J — connector-kind Literal shared with Wave 3G + tests.

Re-exports the same ``ConnectorKind`` / ``CONNECTOR_KINDS`` shape the
ORM module defines in ``control_plane.domain.mcp_outbound`` so callers
on the agent side (Wave 3G ``mcp_client`` connector registry, allow-list
validation, and per-kind dispatch) can import from one place without
reaching into the ORM module or hard-coding the list in three Python
files.

The DB CHECK constraint (``ck_tenant_mcp_configs_connector_kind`` on
the ``0048_tenant_mcp_configs`` migration) is the authoritative
gatekeeper. This module exists so Python code never duplicates the
string literals; both this module and ``mcp_outbound`` import the same
catalog identifiers and assert equality at module-load time so a drift
is impossible to ship without the unit tests failing.

Web side: the display metadata mirror of this catalog lives in
``apps/web/src/lib/mcp-connectors.ts``.
"""

from __future__ import annotations

from typing import Literal

from control_plane.domain.mcp_outbound import (
    CONNECTOR_KINDS as _DOMAIN_CONNECTOR_KINDS,
)

# Re-declared inline (not aliased from the domain module) so:
#   * static type-checkers see the Literal at the agent_kenny call site
#     and narrow correctly without chasing the re-export, and
#   * the brief's stated invariant — ``Literal["slack", "linear",
#     "gdrive", "notion", "github"]`` — is auditable in one screen.
# The runtime ``assert`` below catches any drift between the two
# definitions before a CHECK-constraint failure surfaces in prod.
ConnectorKind = Literal["slack", "linear", "gdrive", "notion", "github"]

CONNECTOR_KINDS: tuple[ConnectorKind, ...] = (
    "slack",
    "linear",
    "gdrive",
    "notion",
    "github",
)

assert CONNECTOR_KINDS == _DOMAIN_CONNECTOR_KINDS, (
    "control_plane.agents.agent_kenny.mcp_connectors.CONNECTOR_KINDS drifted "
    "from control_plane.domain.mcp_outbound.CONNECTOR_KINDS; widen both at "
    "once and update the alembic CHECK constraint "
    "(ck_tenant_mcp_configs_connector_kind)."
)


__all__ = [
    "CONNECTOR_KINDS",
    "ConnectorKind",
]
