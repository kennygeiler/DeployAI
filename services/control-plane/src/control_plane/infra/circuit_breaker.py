"""Generic circuit breaker for outbound dependencies (docs/ops/resilience.md).

Classic three-state machine, one instance per dependency:

- **closed** — calls pass through; ``failure_threshold`` *consecutive*
  failures open the circuit (any success resets the count, so a healthy
  dependency never trips).
- **open** — every ``acquire`` raises :class:`CircuitOpenError` without
  touching the network until ``cooldown_s`` has elapsed.
- **half-open** — after the cooldown, up to ``half_open_max_probes``
  in-flight calls are admitted as probes. A probe success closes the
  circuit; a probe failure re-opens it for another full cooldown.

Single-process semantics, on purpose: state is a process-local object with
no cross-instance coordination — each control-plane replica trips and
recovers independently (same trade-off as the in-memory API rate limiter
in :mod:`control_plane.infra.rate_limit`). That is the right shape for a
breaker: it protects *this* process's event loop from stalling on a dead
dependency; fleet-wide backpressure is the dependency's own job.

``failure_threshold <= 0`` disables the breaker: ``acquire`` and the
``record_*`` methods become no-ops and the circuit never opens.

Callers decide what counts as a failure — only record failures that mean
"the dependency is unreachable or erroring" (timeouts, connect errors,
5xx). A 4xx or a malformed body proves the dependency is up; recording it
as success keeps a misconfigured client from masquerading as an outage.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Callable
from enum import IntEnum

from control_plane.config.settings import get_settings
from control_plane.infra.observability import observe_circuit_open, observe_circuit_state

logger = logging.getLogger(__name__)

DEFAULT_FAILURE_THRESHOLD = 5
DEFAULT_COOLDOWN_S = 30.0
DEFAULT_HALF_OPEN_MAX_PROBES = 1

# Monotonic-seconds source. Injectable so state-machine tests advance time
# deterministically instead of sleeping.
Clock = Callable[[], float]


class CircuitState(IntEnum):
    """Gauge values for ``deployai_circuit_state`` — keep the mapping stable."""

    CLOSED = 0
    HALF_OPEN = 1
    OPEN = 2


class CircuitOpenError(Exception):
    """The circuit is open — the call was rejected without a network attempt.

    ``retry_after_s`` is the time until the next probe would be admitted
    (0.0 when the breaker is half-open but the probe budget is already
    in flight — a retry is imminent, just not through this caller).
    """

    def __init__(self, dependency: str, *, retry_after_s: float) -> None:
        super().__init__(f"circuit open for {dependency!r}; next probe in {retry_after_s:.1f}s")
        self.dependency = dependency
        self.retry_after_s = retry_after_s


class CircuitBreaker:
    """Async-safe breaker for one named dependency.

    All state mutations happen under one :class:`asyncio.Lock`, so two
    coroutines racing the half-open transition admit exactly one probe.
    The lock is per-event-loop like everything else in this process; see
    the module docstring for the single-process caveat.

    Usage contract: every successful ``acquire`` MUST be balanced by
    exactly one ``record_success`` or ``record_failure`` — the half-open
    probe budget is reserved at ``acquire`` time and only released by the
    matching ``record_*`` call.
    """

    def __init__(
        self,
        dependency: str,
        *,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        cooldown_s: float = DEFAULT_COOLDOWN_S,
        half_open_max_probes: int = DEFAULT_HALF_OPEN_MAX_PROBES,
        clock: Clock = time.monotonic,
    ) -> None:
        if cooldown_s <= 0:
            raise ValueError(f"cooldown_s must be positive; got {cooldown_s!r}")
        if half_open_max_probes < 1:
            raise ValueError(f"half_open_max_probes must be >= 1; got {half_open_max_probes!r}")
        self._dependency = dependency
        self._failure_threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._half_open_max_probes = half_open_max_probes
        self._clock = clock
        self._lock = asyncio.Lock()
        self._state = CircuitState.CLOSED
        self._consecutive_failures = 0
        self._opened_at = 0.0
        self._probes_in_flight = 0
        if self.enabled:
            observe_circuit_state(dependency, int(CircuitState.CLOSED))

    @property
    def dependency(self) -> str:
        return self._dependency

    @property
    def enabled(self) -> bool:
        return self._failure_threshold > 0

    @property
    def state(self) -> CircuitState:
        return self._state

    async def acquire(self) -> None:
        """Admit one call or raise :class:`CircuitOpenError`.

        Open + cooldown elapsed transitions to half-open and admits this
        caller as the probe; open + cooldown pending raises with the
        remaining wait so callers can surface "retry in Ns".
        """
        if not self.enabled:
            return
        async with self._lock:
            if self._state is CircuitState.OPEN:
                remaining = self._opened_at + self._cooldown_s - self._clock()
                if remaining > 0:
                    raise CircuitOpenError(self._dependency, retry_after_s=remaining)
                self._transition(CircuitState.HALF_OPEN)
                self._probes_in_flight = 0
            if self._state is CircuitState.HALF_OPEN:
                if self._probes_in_flight >= self._half_open_max_probes:
                    raise CircuitOpenError(self._dependency, retry_after_s=0.0)
                self._probes_in_flight += 1

    async def record_success(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._probes_in_flight = max(0, self._probes_in_flight - 1)
                self._transition(CircuitState.CLOSED)
            self._consecutive_failures = 0

    async def record_failure(self) -> None:
        if not self.enabled:
            return
        async with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                # Probe failed — full cooldown restarts.
                self._probes_in_flight = max(0, self._probes_in_flight - 1)
                self._open()
                return
            if self._state is CircuitState.OPEN:
                # A call admitted before the trip finished after it; the
                # circuit is already open, nothing to count.
                return
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._open()

    # ----- internals (call under self._lock) --------------------------------

    def _open(self) -> None:
        self._opened_at = self._clock()
        self._consecutive_failures = 0
        self._transition(CircuitState.OPEN)
        observe_circuit_open(self._dependency)

    def _transition(self, new_state: CircuitState) -> None:
        if new_state is self._state:
            return
        old_state = self._state
        self._state = new_state
        observe_circuit_state(self._dependency, int(new_state))
        logger.warning(
            "circuit_breaker dependency=%s transition=%s->%s cooldown_s=%.1f",
            self._dependency,
            old_state.name.lower(),
            new_state.name.lower(),
            self._cooldown_s,
        )


class CircuitBreakerRegistry:
    """Lazily builds one :class:`CircuitBreaker` per dependency name.

    Shared config across all breakers it creates; the MCP client uses one
    registry to get a breaker PER connector so a dead Slack upstream
    never blocks GitHub calls. ``get`` runs on one event loop (no await
    between lookup and insert) so the dict needs no lock.
    """

    def __init__(
        self,
        *,
        failure_threshold: int = DEFAULT_FAILURE_THRESHOLD,
        cooldown_s: float = DEFAULT_COOLDOWN_S,
        half_open_max_probes: int = DEFAULT_HALF_OPEN_MAX_PROBES,
        clock: Clock = time.monotonic,
    ) -> None:
        self._failure_threshold = failure_threshold
        self._cooldown_s = cooldown_s
        self._half_open_max_probes = half_open_max_probes
        self._clock = clock
        self._breakers: dict[str, CircuitBreaker] = {}

    def get(self, dependency: str) -> CircuitBreaker:
        breaker = self._breakers.get(dependency)
        if breaker is None:
            breaker = CircuitBreaker(
                dependency,
                failure_threshold=self._failure_threshold,
                cooldown_s=self._cooldown_s,
                half_open_max_probes=self._half_open_max_probes,
                clock=self._clock,
            )
            self._breakers[dependency] = breaker
        return breaker


def registry_from_settings() -> CircuitBreakerRegistry:
    """Registry configured from ``DEPLOYAI_CIRCUIT_*`` env (via settings)."""
    settings = get_settings()
    return CircuitBreakerRegistry(
        failure_threshold=settings.circuit_failure_threshold,
        cooldown_s=settings.circuit_cooldown_s,
    )


def breaker_from_settings(dependency: str) -> CircuitBreaker:
    """One standalone breaker configured from ``DEPLOYAI_CIRCUIT_*`` env."""
    settings = get_settings()
    return CircuitBreaker(
        dependency,
        failure_threshold=settings.circuit_failure_threshold,
        cooldown_s=settings.circuit_cooldown_s,
    )


__all__ = [
    "DEFAULT_COOLDOWN_S",
    "DEFAULT_FAILURE_THRESHOLD",
    "DEFAULT_HALF_OPEN_MAX_PROBES",
    "CircuitBreaker",
    "CircuitBreakerRegistry",
    "CircuitOpenError",
    "CircuitState",
    "breaker_from_settings",
    "registry_from_settings",
]
