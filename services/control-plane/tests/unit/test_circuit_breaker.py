"""State-machine tests for the generic outbound circuit breaker.

Deterministic via the injectable clock — no real sleeping. Dependency
names are unique per test because the Prometheus gauge/counter labels are
process-global.
"""

from __future__ import annotations

import asyncio

import pytest
from prometheus_client import REGISTRY

from control_plane.infra.circuit_breaker import (
    CircuitBreaker,
    CircuitBreakerRegistry,
    CircuitOpenError,
    CircuitState,
)


class FakeClock:
    def __init__(self, start: float = 100.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _breaker(dependency: str, clock: FakeClock, **overrides: object) -> CircuitBreaker:
    kwargs: dict[str, object] = {"failure_threshold": 3, "cooldown_s": 30.0}
    kwargs.update(overrides)
    return CircuitBreaker(dependency, clock=clock, **kwargs)  # type: ignore[arg-type]


async def _trip(breaker: CircuitBreaker, n: int) -> None:
    for _ in range(n):
        await breaker.acquire()
        await breaker.record_failure()


# ---------------------------------------------------------------------------
# Closed-state behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_success_resets_consecutive_failure_count() -> None:
    clock = FakeClock()
    breaker = _breaker("t-reset", clock)
    await _trip(breaker, 2)
    await breaker.acquire()
    await breaker.record_success()
    # Two more failures: without the reset this would be the 4th/5th and trip.
    await _trip(breaker, 2)
    assert breaker.state is CircuitState.CLOSED
    await breaker.acquire()  # still admitting


@pytest.mark.asyncio
async def test_threshold_consecutive_failures_open_the_circuit() -> None:
    clock = FakeClock()
    breaker = _breaker("t-trip", clock)
    await _trip(breaker, 3)
    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError) as excinfo:
        await breaker.acquire()
    assert excinfo.value.dependency == "t-trip"
    assert 0 < excinfo.value.retry_after_s <= 30.0


# ---------------------------------------------------------------------------
# Cooldown + half-open
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cooldown_elapsed_admits_probe_and_success_closes() -> None:
    clock = FakeClock()
    breaker = _breaker("t-close", clock)
    await _trip(breaker, 3)
    clock.advance(30.0)
    await breaker.acquire()  # the probe
    assert breaker.state is CircuitState.HALF_OPEN
    await breaker.record_success()
    assert breaker.state is CircuitState.CLOSED
    await breaker.acquire()  # closed again — admits freely


@pytest.mark.asyncio
async def test_half_open_probe_failure_reopens_for_full_cooldown() -> None:
    clock = FakeClock()
    breaker = _breaker("t-reopen", clock)
    await _trip(breaker, 3)
    clock.advance(30.0)
    await breaker.acquire()
    await breaker.record_failure()
    assert breaker.state is CircuitState.OPEN
    with pytest.raises(CircuitOpenError) as excinfo:
        await breaker.acquire()
    # The cooldown restarted at the probe failure, not the original trip.
    assert excinfo.value.retry_after_s == pytest.approx(30.0)
    clock.advance(30.0)
    await breaker.acquire()
    assert breaker.state is CircuitState.HALF_OPEN


@pytest.mark.asyncio
async def test_open_before_cooldown_reports_remaining_wait() -> None:
    clock = FakeClock()
    breaker = _breaker("t-wait", clock)
    await _trip(breaker, 3)
    clock.advance(10.0)
    with pytest.raises(CircuitOpenError) as excinfo:
        await breaker.acquire()
    assert excinfo.value.retry_after_s == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Disabled via threshold 0
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_threshold_zero_disables_breaker() -> None:
    clock = FakeClock()
    breaker = _breaker("t-disabled", clock, failure_threshold=0)
    assert not breaker.enabled
    for _ in range(20):
        await breaker.acquire()
        await breaker.record_failure()
    assert breaker.state is CircuitState.CLOSED
    await breaker.acquire()  # never raises


# ---------------------------------------------------------------------------
# Concurrency: half-open admits exactly one probe
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_two_coroutines_racing_half_open_admit_one_probe() -> None:
    clock = FakeClock()
    breaker = _breaker("t-race", clock)
    await _trip(breaker, 3)
    clock.advance(30.0)
    results = await asyncio.gather(
        breaker.acquire(),
        breaker.acquire(),
        return_exceptions=True,
    )
    rejections = [r for r in results if isinstance(r, CircuitOpenError)]
    assert len(rejections) == 1, "exactly one coroutine wins the probe slot"
    assert breaker.state is CircuitState.HALF_OPEN
    # The winning probe succeeds → circuit closes.
    await breaker.record_success()
    assert breaker.state is CircuitState.CLOSED


# ---------------------------------------------------------------------------
# Registry + metrics
# ---------------------------------------------------------------------------


def test_registry_returns_one_breaker_per_dependency() -> None:
    registry = CircuitBreakerRegistry(failure_threshold=2, cooldown_s=5.0)
    slack = registry.get("mcp:slack")
    assert registry.get("mcp:slack") is slack
    assert registry.get("mcp:github") is not slack
    assert slack.dependency == "mcp:slack"


@pytest.mark.asyncio
async def test_open_transition_increments_counter_and_gauge() -> None:
    clock = FakeClock()
    breaker = _breaker("t-metrics", clock)
    await _trip(breaker, 3)
    opens = REGISTRY.get_sample_value("deployai_circuit_opens_total", {"dependency": "t-metrics"})
    state = REGISTRY.get_sample_value("deployai_circuit_state", {"dependency": "t-metrics"})
    assert opens == 1.0
    assert state == float(CircuitState.OPEN)
    clock.advance(30.0)
    await breaker.acquire()
    assert REGISTRY.get_sample_value("deployai_circuit_state", {"dependency": "t-metrics"}) == float(
        CircuitState.HALF_OPEN
    )
    await breaker.record_success()
    assert REGISTRY.get_sample_value("deployai_circuit_state", {"dependency": "t-metrics"}) == float(
        CircuitState.CLOSED
    )
