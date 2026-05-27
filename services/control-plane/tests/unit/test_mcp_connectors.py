"""v2 Phase 5 Wave 3J — connector-kind catalog parity tests.

Locks in the invariant that the agent-side ``CONNECTOR_KINDS`` tuple
matches the domain-side tuple (which mirrors the alembic CHECK
constraint ``ck_tenant_mcp_configs_connector_kind`` on
``0048_tenant_mcp_configs``). If any of these tests fail, the catalog
has drifted and the next attempt to insert a row with the new kind
will be rejected by Postgres before the test suite ever sees it — so
we'd rather find the drift here.
"""

from __future__ import annotations

import typing

from control_plane.agents.agent_kenny.mcp_connectors import (
    CONNECTOR_KINDS,
    ConnectorKind,
)
from control_plane.domain.mcp_outbound import (
    CONNECTOR_KINDS as DOMAIN_CONNECTOR_KINDS,
)


def test_connector_kinds_length_is_five() -> None:
    assert len(CONNECTOR_KINDS) == 5


def test_connector_kinds_matches_domain_catalog() -> None:
    # Order is significant: the web catalog (apps/web/src/lib/
    # mcp-connectors.ts) iterates in this same order so the UI + the
    # server-side enumeration line up.
    assert CONNECTOR_KINDS == DOMAIN_CONNECTOR_KINDS


def test_every_value_is_a_valid_connector_kind_literal() -> None:
    # ``typing.get_args`` returns the Literal's allowed values verbatim.
    # Every member of CONNECTOR_KINDS must appear in that set, and the
    # set must not contain anything CONNECTOR_KINDS doesn't list.
    literal_args = set(typing.get_args(ConnectorKind))
    assert set(CONNECTOR_KINDS) == literal_args


def test_connector_kinds_has_no_duplicates() -> None:
    assert len(set(CONNECTOR_KINDS)) == len(CONNECTOR_KINDS)


def test_known_kinds_are_present() -> None:
    # Spell out the v1 catalog so a re-ordering or accidental drop is
    # caught with a readable failure rather than just a length mismatch.
    for kind in ("slack", "linear", "gdrive", "notion", "github"):
        assert kind in CONNECTOR_KINDS
