"""v2 Phase 5 Wave 2F — outbound-MCP rate limiter unit tests.

Covers the two caps and the per-turn / per-tenant / per-tool scoping
that :class:`InMemoryMcpRateLimiter` enforces. All caps and the clock
are injected so the tests are deterministic + fast (no real sleeps).
"""

from __future__ import annotations

import uuid

import pytest

from control_plane.agents.agent_kenny.mcp_rate_limit import (
    DEFAULT_PER_MINUTE_CAP,
    DEFAULT_PER_TURN_CAP,
    InMemoryMcpRateLimiter,
    current_turn_id_var,
)


def _make_limiter(per_turn: int = 10, per_minute: int = 60) -> InMemoryMcpRateLimiter:
    """Build a limiter with a fixed clock at t=1000.0 (mutable via closure)."""
    return InMemoryMcpRateLimiter(
        per_turn_cap=per_turn,
        per_minute_cap=per_minute,
        clock=lambda: 1000.0,
    )


def test_defaults_match_documented_values() -> None:
    assert DEFAULT_PER_TURN_CAP == 10
    assert DEFAULT_PER_MINUTE_CAP == 60


@pytest.mark.asyncio
async def test_per_turn_cap_blocks_eleventh_call_in_same_turn() -> None:
    limiter = _make_limiter(per_turn=10, per_minute=1000)
    tenant = uuid.uuid4()
    turn = uuid.uuid4()
    limiter.open_turn(turn, tenant)
    token = current_turn_id_var.set(turn)
    try:
        for _ in range(10):
            assert await limiter.acquire(tenant, "slack.search_messages") is True
        # 11th call in the same turn must be denied.
        assert await limiter.acquire(tenant, "slack.search_messages") is False
        # A different tool in the same turn is also denied — the per-turn
        # cap is a *total* external-call cap, not per-tool.
        assert await limiter.acquire(tenant, "linear.list_issues") is False
    finally:
        current_turn_id_var.reset(token)
        limiter.close_turn(turn)


@pytest.mark.asyncio
async def test_per_minute_cap_blocks_61st_call_across_turns() -> None:
    """Per-minute cap survives turn boundaries (it's tenant+tool-scoped)."""
    limiter = _make_limiter(per_turn=1000, per_minute=60)
    tenant = uuid.uuid4()

    # Burn 60 calls across many turns (so the per-turn cap can't kick in).
    for _ in range(60):
        turn = uuid.uuid4()
        limiter.open_turn(turn, tenant)
        token = current_turn_id_var.set(turn)
        try:
            assert await limiter.acquire(tenant, "slack.search_messages") is True
        finally:
            current_turn_id_var.reset(token)
            limiter.close_turn(turn)

    # 61st (anywhere — new turn, no turn at all, same turn — same answer).
    assert await limiter.acquire(tenant, "slack.search_messages") is False


@pytest.mark.asyncio
async def test_per_minute_window_slides_forward() -> None:
    """After 60s the early entries fall out of the window and slots free up."""
    fake_now = {"t": 1000.0}
    limiter = InMemoryMcpRateLimiter(per_turn_cap=1000, per_minute_cap=2, clock=lambda: fake_now["t"])
    tenant = uuid.uuid4()

    assert await limiter.acquire(tenant, "slack.x") is True  # t=1000
    fake_now["t"] = 1010.0
    assert await limiter.acquire(tenant, "slack.x") is True  # t=1010 (2 in window)
    assert await limiter.acquire(tenant, "slack.x") is False  # capped

    # Slide the clock past the first call's expiry (t=1000+60=1060).
    fake_now["t"] = 1061.0
    assert await limiter.acquire(tenant, "slack.x") is True  # window now [1010, 1061]


@pytest.mark.asyncio
async def test_different_tenants_do_not_share_buckets() -> None:
    limiter = _make_limiter(per_turn=1000, per_minute=1)
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    assert await limiter.acquire(tenant_a, "slack.x") is True
    assert await limiter.acquire(tenant_a, "slack.x") is False
    # Tenant B has an independent bucket.
    assert await limiter.acquire(tenant_b, "slack.x") is True
    assert await limiter.acquire(tenant_b, "slack.x") is False


@pytest.mark.asyncio
async def test_different_tools_within_same_tenant_do_not_share_buckets() -> None:
    limiter = _make_limiter(per_turn=1000, per_minute=1)
    tenant = uuid.uuid4()

    assert await limiter.acquire(tenant, "slack.search_messages") is True
    assert await limiter.acquire(tenant, "slack.search_messages") is False
    # Different tool name on the same tenant gets its own bucket.
    assert await limiter.acquire(tenant, "linear.list_issues") is True
    assert await limiter.acquire(tenant, "linear.list_issues") is False


@pytest.mark.asyncio
async def test_release_is_noop_and_does_not_crash() -> None:
    """``release`` is part of the Protocol but a token-bucket no-op."""
    limiter = _make_limiter(per_turn=1, per_minute=1)
    tenant = uuid.uuid4()

    assert await limiter.acquire(tenant, "slack.x") is True
    # ``release`` doesn't free the slot back — the next acquire is still
    # denied because the per-minute window still contains the timestamp.
    await limiter.release(tenant, "slack.x")
    assert await limiter.acquire(tenant, "slack.x") is False
    # And calling it on an unknown (tenant, tool) pair must not crash.
    await limiter.release(uuid.uuid4(), "unseen.tool")


@pytest.mark.asyncio
async def test_open_turn_scopes_per_turn_count_correctly() -> None:
    """Two consecutive turns each get their own per-turn budget."""
    limiter = _make_limiter(per_turn=2, per_minute=1000)
    tenant = uuid.uuid4()

    # Turn 1: burn through the per-turn cap.
    turn1 = uuid.uuid4()
    limiter.open_turn(turn1, tenant)
    token1 = current_turn_id_var.set(turn1)
    try:
        assert await limiter.acquire(tenant, "slack.x") is True
        assert await limiter.acquire(tenant, "slack.x") is True
        assert await limiter.acquire(tenant, "slack.x") is False  # capped
    finally:
        current_turn_id_var.reset(token1)
        limiter.close_turn(turn1)

    # Turn 2: fresh budget.
    turn2 = uuid.uuid4()
    limiter.open_turn(turn2, tenant)
    token2 = current_turn_id_var.set(turn2)
    try:
        assert await limiter.acquire(tenant, "slack.x") is True
        assert await limiter.acquire(tenant, "slack.x") is True
        assert await limiter.acquire(tenant, "slack.x") is False
    finally:
        current_turn_id_var.reset(token2)
        limiter.close_turn(turn2)


@pytest.mark.asyncio
async def test_close_turn_is_idempotent_for_unknown_turn() -> None:
    limiter = _make_limiter()
    # Must not crash even though we never called open_turn for this id.
    limiter.close_turn(uuid.uuid4())


@pytest.mark.asyncio
async def test_no_open_turn_disables_per_turn_cap_but_keeps_minute_cap() -> None:
    """Background callers without a turn-id only see the per-minute cap.

    The ContextVar defaults to ``None``; ``acquire`` treats that as "no
    turn to charge against" and skips the per-turn check. The per-minute
    cap still applies.
    """
    limiter = _make_limiter(per_turn=2, per_minute=5)
    tenant = uuid.uuid4()
    # Sanity: ContextVar is None outside any open_turn / set() block.
    assert current_turn_id_var.get() is None

    # 5 calls allowed (per-minute cap), 6th denied. Per-turn cap of 2 is
    # NOT applied because no turn id is in the ContextVar.
    for _ in range(5):
        assert await limiter.acquire(tenant, "slack.x") is True
    assert await limiter.acquire(tenant, "slack.x") is False


def test_env_vars_override_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_TURN", "3")
    monkeypatch.setenv("DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_MINUTE", "9")
    limiter = InMemoryMcpRateLimiter()
    assert limiter.per_turn_cap == 3
    assert limiter.per_minute_cap == 9


def test_env_vars_ignore_bogus_values(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_TURN", "not-a-number")
    monkeypatch.setenv("DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_MINUTE", "-5")
    limiter = InMemoryMcpRateLimiter()
    assert limiter.per_turn_cap == DEFAULT_PER_TURN_CAP
    assert limiter.per_minute_cap == DEFAULT_PER_MINUTE_CAP
