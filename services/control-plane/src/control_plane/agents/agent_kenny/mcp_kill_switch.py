"""Concrete :class:`DbMcpKillSwitch` for outbound MCP (Wave 2F).

Implements the ``McpKillSwitch`` Protocol that Wave 2D's
``agents/agent_kenny/mcp_client.py`` calls before every external
``tools/call``. Returning ``True`` causes the client to raise
:class:`control_plane.agents.agent_kenny.mcp_types.McpOutboundDisabled`
and skip the network round-trip.

The flag lives on ``app_tenants.mcp_outbound_disabled`` (one row per
tenant) — see migration ``20260613_0049_mcp_outbound_kill_switch.py``
for the rationale (threat-model §5.5 Option B).

Hot-path posture
----------------
Every outbound tool call must check this. To keep the per-call cost
near zero we maintain an in-memory TTL cache keyed by ``tenant_id``:

  - Cache hit (entry younger than ``CACHE_TTL_SECONDS``) → return cached value.
  - Cache miss → single ``SELECT`` from ``app_tenants``, then cache.

We intentionally do **not** invalidate the cache on writes. Threat-model
§5.5 explicitly accepts "order-of-seconds" propagation delay for v1, in
exchange for not needing a pub/sub channel or Redis. When the admin
flips the kill switch the worst case is a ~5s window where in-flight
calls still go through — well inside the human reaction time of the
on-call operator who flipped the switch in the first place.

Wave 3G will wire one process-wide instance at agent-loop construction
time. The cache is per-instance, so a multi-replica deployment would
each maintain their own 5s view — still bounded by ``CACHE_TTL_SECONDS``.
"""

from __future__ import annotations

import time
import uuid
from typing import Final

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from control_plane.domain.app_identity.models import AppTenant

CACHE_TTL_SECONDS: Final[float] = 5.0


class DbMcpKillSwitch:
    """``app_tenants.mcp_outbound_disabled``-backed kill switch with 5s cache.

    Matches the ``McpKillSwitch`` Protocol shape Wave 2D's mcp_client
    consumes::

        async def is_outbound_disabled(self, tenant_id: UUID) -> bool: ...
    """

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        cache_ttl_seconds: float = CACHE_TTL_SECONDS,
        # Injected for tests so a deterministic clock can drive cache expiry
        # without sleeping. Defaults to ``time.monotonic`` which is immune
        # to wall-clock jumps.
        clock: object | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._ttl = cache_ttl_seconds
        # value: (disabled_bool, fetched_at_monotonic)
        self._cache: dict[uuid.UUID, tuple[bool, float]] = {}
        self._clock = clock or time.monotonic

    async def is_outbound_disabled(self, tenant_id: uuid.UUID) -> bool:
        now = float(self._clock())  # type: ignore[operator]
        cached = self._cache.get(tenant_id)
        if cached is not None:
            disabled, fetched_at = cached
            if now - fetched_at < self._ttl:
                return disabled

        async with self._session_factory() as session:
            stmt = select(AppTenant.mcp_outbound_disabled).where(AppTenant.id == tenant_id)
            value = (await session.execute(stmt)).scalar_one_or_none()

        # Unknown tenant → fail-open on the kill switch. The allow-list
        # check in Wave 2D's mcp_client still fails closed because an
        # unknown tenant has no ``tenant_mcp_configs`` rows, so no tools
        # are merged into the registry in the first place. We don't want
        # a transient DB blip on an unknown id to escalate to a misleading
        # "kill switch engaged" message.
        disabled = bool(value) if value is not None else False
        self._cache[tenant_id] = (disabled, now)
        return disabled

    def invalidate(self, tenant_id: uuid.UUID) -> None:
        """Drop the cached entry for one tenant.

        Optional — the admin write path is welcome to call this after a
        flip for callers that want sub-5s propagation. The Protocol
        Wave 2D consumes does not require it; threat-model §5.5 accepts
        the 5s window as the default behaviour.
        """
        self._cache.pop(tenant_id, None)


__all__ = ["CACHE_TTL_SECONDS", "DbMcpKillSwitch"]
