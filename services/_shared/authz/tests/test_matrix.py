from __future__ import annotations

import pytest

from deployai_authz import AuthActor, can_access, is_allowed, matrix_allowed


def test_platform_admin_ingest_runs() -> None:
    d = is_allowed("platform_admin", "ingest:view_runs")
    assert d.allow is True
    assert d.code == "ok"


def test_auditor_no_promote() -> None:
    d = is_allowed("external_auditor", "admin:promote_schema")
    assert d.allow is False


def test_can_access_cross_tenant() -> None:
    actor = AuthActor(role="customer_admin", tenant_id="aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    d = can_access(
        actor,
        "canonical:read",
        {"kind": "tenant", "id": "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"},
        skip_audit=True,
    )
    assert d.allow is False


def test_matrix_parity_sample() -> None:
    assert matrix_allowed("deployment_strategist", "ingest:sync") is True
    assert matrix_allowed("deployment_strategist", "integration:kill_switch") is True
    assert matrix_allowed("deployment_strategist", "break_glass:invoke") is False
    assert matrix_allowed("customer_admin", "integration:kill_switch") is False
    assert matrix_allowed("pending_assignment", "canonical:read") is False


@pytest.mark.parametrize(
    ("role", "action", "expect"),
    [
        ("platform_admin", "break_glass:invoke", True),
        ("customer_admin", "break_glass:invoke", False),
        ("external_auditor", "canonical:read", True),
        ("external_auditor", "foia:export", True),
    ],
)
def test_role_action(
    role: str,
    action: str,
    expect: bool,
) -> None:
    d = is_allowed(role, action)  # type: ignore[arg-type]
    assert d.allow is expect
