"""In-memory token-bucket rate limiter for outbound MCP tool calls (Wave 2F).

Implements the ``McpRateLimiter`` Protocol that Wave 2D's
``agents/agent_kenny/mcp_client.py`` consumes::

    async def acquire(self, tenant_id: UUID, tool_name: str) -> bool: ...
    async def release(self, tenant_id: UUID, tool_name: str) -> None: ...

``acquire`` returns ``False`` when the call would breach **either** of
two independent caps. The client maps that ``False`` to
:class:`control_plane.agents.agent_kenny.mcp_types.McpRateLimited` and
surfaces it to the LLM as a "try again in a moment" tool result, so the
agent loop can either back off or pivot to a different tool.

Two caps
--------
1. **Per-turn cap** — ``DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_TURN``
   (default 10). Counts every call (any tool) inside a single agent
   turn. Bounded by the same scope-v2 §6.2 "no runaway loops" intent
   that also enforces ``MAX_TOOL_CALLS_PER_TURN`` for built-in tools;
   here it's the *external* spend that's being bounded. The turn is
   identified by a :class:`contextvars.ContextVar` that callers set with
   :meth:`open_turn` at the start of an agent turn and clear with
   :meth:`close_turn` at the end (mirrors
   ``infra/request_context.request_id_var`` style).

2. **Per-tenant per-tool per-minute cap** —
   ``DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_MINUTE`` (default 60). A
   sliding-window counter scoped to ``(tenant_id, tool_name)``. Stops a
   single tool from being hammered across many turns (e.g. a runaway
   background job that calls ``slack.search_messages`` 1000x/min).

Both caps must clear for ``acquire`` to return ``True``.

In-memory by design
-------------------
The control-plane runs as a single process today. When (if) we go
multi-replica, this module moves to Redis — the bucket math is
trivially Lua-portable, and the Protocol stays unchanged so the swap is
a single-line wiring change in Wave 3G's agent-loop builder.

TODO(multi-replica): port to Redis-backed buckets keyed by
``mcp:rl:{tenant}:{tool}:{minute_epoch}``. Until then the in-memory
implementation is *the* correct one — putting a Redis client on the
hot path before we need it would just add latency and a single point of
failure to a feature that is, in v1, a defence-in-depth measure.

``release`` is a no-op for the token-bucket model (the "release" of a
slot happens automatically when the per-minute window slides forward).
We accept it as part of the Protocol so the same shape works for a
future semaphore-style limiter without breaking the client.
"""

from __future__ import annotations

import os
import time
import uuid
from collections.abc import Callable
from contextvars import ContextVar
from threading import Lock
from typing import Final

DEFAULT_PER_TURN_CAP: Final[int] = 10
DEFAULT_PER_MINUTE_CAP: Final[int] = 60

_PER_TURN_ENV: Final[str] = "DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_TURN"
_PER_MINUTE_ENV: Final[str] = "DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_MINUTE"

# ContextVar set at agent-turn boundary by Wave 3G's loop. ``acquire``
# reads it to attribute the call to a per-turn bucket. ``None`` means
# "no turn open" — the limiter falls back to enforcing only the
# per-minute cap, which is correct for background callers that aren't
# inside an agent turn (e.g. an admin smoke-test endpoint).
current_turn_id_var: ContextVar[uuid.UUID | None] = ContextVar("mcp_outbound_current_turn_id", default=None)


def _read_int_env(name: str, default: int) -> int:
    """Parse a positive int env var; fall back to ``default`` on any error."""
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        parsed = int(raw)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


class InMemoryMcpRateLimiter:
    """Per-tenant per-tool token bucket + per-turn counter (single-process)."""

    def __init__(
        self,
        *,
        per_turn_cap: int | None = None,
        per_minute_cap: int | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._per_turn_cap = (
            per_turn_cap if per_turn_cap is not None else _read_int_env(_PER_TURN_ENV, DEFAULT_PER_TURN_CAP)
        )
        self._per_minute_cap = (
            per_minute_cap if per_minute_cap is not None else _read_int_env(_PER_MINUTE_ENV, DEFAULT_PER_MINUTE_CAP)
        )
        self._clock = clock or time.monotonic
        # Single coarse-grained lock — the limiter is in the request hot
        # path but the per-call work is microseconds of arithmetic, so
        # contention is dwarfed by the surrounding HTTP I/O. If profiling
        # ever flags this, swap to a per-tenant lock map. asyncio is
        # single-threaded by default so the lock is technically redundant
        # under uvicorn-uvloop, but it documents intent and protects the
        # one-off background-thread caller (e.g. admin tooling).
        self._lock = Lock()
        # Per-(tenant, tool) sliding window: list of timestamps in the
        # past minute. Old entries are evicted on each ``acquire``.
        self._minute_window: dict[tuple[uuid.UUID, str], list[float]] = {}
        # Per-turn counter: turn_id → calls-made-this-turn. We don't
        # bother bucketing by tool inside a turn because the per-turn
        # cap is intentionally a *total* cap on external spend per turn.
        self._turn_counts: dict[uuid.UUID, int] = {}
        # Reverse map turn_id → tenant_id so ``close_turn`` doesn't need
        # the tenant. Mostly a tests-and-observability convenience.
        self._turn_tenant: dict[uuid.UUID, uuid.UUID] = {}

    # ------------------------------------------------------------------
    # Protocol surface (called by Wave 2D's mcp_client per outbound call)
    # ------------------------------------------------------------------

    async def acquire(self, tenant_id: uuid.UUID, tool_name: str) -> bool:
        now = self._clock()
        turn_id = current_turn_id_var.get()
        with self._lock:
            # --- per-minute sliding window
            key = (tenant_id, tool_name)
            window = self._minute_window.setdefault(key, [])
            cutoff = now - 60.0
            # Evict expired entries in-place. Python list.pop(0) is O(n)
            # but n is bounded by the per-minute cap (≤60 in defaults).
            while window and window[0] <= cutoff:
                window.pop(0)
            if len(window) >= self._per_minute_cap:
                return False

            # --- per-turn cap (only enforced when a turn is open)
            if turn_id is not None:
                turn_count = self._turn_counts.get(turn_id, 0)
                if turn_count >= self._per_turn_cap:
                    return False

            # Both caps cleared — record the consumption atomically so
            # parallel ``acquire`` calls in the same turn can't both
            # squeak past the cap (would race without the lock).
            window.append(now)
            if turn_id is not None:
                self._turn_counts[turn_id] = self._turn_counts.get(turn_id, 0) + 1
        return True

    async def release(self, tenant_id: uuid.UUID, tool_name: str) -> None:
        """No-op for token-bucket. Slots expire as the window slides.

        Kept for Protocol parity with potential future semaphore-style
        limiters (e.g. "max concurrent calls per tenant"). Wave 2D calls
        ``release`` in the ``finally`` block of every tool call, so we
        must accept it without crashing — but the bucket itself doesn't
        free a slot here.
        """
        del tenant_id, tool_name  # unused: documents the Protocol shape

    # ------------------------------------------------------------------
    # Turn lifecycle (called by Wave 3G's loop at agent turn boundaries)
    # ------------------------------------------------------------------

    def open_turn(self, turn_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        """Register a new agent turn and reset its per-turn counter.

        Caller must also ``current_turn_id_var.set(turn_id)`` for the
        ContextVar so ``acquire`` can find the active turn. This
        bookkeeping method does NOT touch the ContextVar so the caller
        retains the reset-token needed for symmetric teardown.
        """
        with self._lock:
            self._turn_counts[turn_id] = 0
            self._turn_tenant[turn_id] = tenant_id

    def close_turn(self, turn_id: uuid.UUID) -> None:
        """Drop the per-turn counter for a closed turn.

        Safe to call for an unknown ``turn_id`` (idempotent).
        """
        with self._lock:
            self._turn_counts.pop(turn_id, None)
            self._turn_tenant.pop(turn_id, None)

    # ------------------------------------------------------------------
    # Test-and-debug observability (not part of the Protocol)
    # ------------------------------------------------------------------

    @property
    def per_turn_cap(self) -> int:
        return self._per_turn_cap

    @property
    def per_minute_cap(self) -> int:
        return self._per_minute_cap


__all__ = [
    "DEFAULT_PER_MINUTE_CAP",
    "DEFAULT_PER_TURN_CAP",
    "InMemoryMcpRateLimiter",
    "current_turn_id_var",
]
