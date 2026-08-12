from __future__ import annotations

import pytest

from deployai_authz import (
    AuthActor,
    TenantScopePolicyError,
    can_access,
    is_allowed,
    matrix_allowed,
)

T_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
T_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


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
        ("external_auditor", "canonical:read", False),
        ("external_auditor", "foia:export", True),
        ("fde", "canonical:read", True),
        ("fde", "break_glass:invoke", False),
        ("biz_dev", "canonical:read", True),
        ("biz_dev", "ingest:view_runs", False),
        # demo_guest (Wave 4S): read-only guest for the public demo workspace.
        ("demo_guest", "canonical:read", True),
        ("demo_guest", "override:submit", False),
        ("demo_guest", "ingest:view_runs", False),
        ("demo_guest", "ingest:sync", False),
        ("demo_guest", "integration:kill_switch", False),
        ("demo_guest", "scim:manage", False),
        ("demo_guest", "foia:export", False),
        ("demo_guest", "break_glass:invoke", False),
        ("demo_guest", "solidification:promote", False),
        ("demo_guest", "admin:promote_schema", False),
    ],
)
def test_role_action(
    role: str,
    action: str,
    expect: bool,
) -> None:
    d = is_allowed(role, action)  # type: ignore[arg-type]
    assert d.allow is expect


# --- Wave 1 ticket A5: tenant comparison for every resource kind ---


@pytest.mark.parametrize(
    ("role", "actor_tenant", "resource_tenant", "expect"),
    [
        ("deployment_strategist", T_A, T_A, True),
        ("deployment_strategist", T_A, T_B, False),
        ("customer_admin", T_A, T_B, False),
        ("fde", T_A, T_B, False),
        # demo_guest reads only inside the disposable demo tenant
        ("demo_guest", T_A, T_A, True),
        ("demo_guest", T_A, T_B, False),
        # platform_admin is exempt from the cross-tenant block (support/ops role)
        ("platform_admin", T_A, T_B, True),
        # actor without a tenant: only the both-present-and-differ rule applies
        ("deployment_strategist", None, T_A, True),
    ],
)
def test_cross_tenant_on_canonical_memory(
    role: str,
    actor_tenant: str | None,
    resource_tenant: str,
    expect: bool,
) -> None:
    actor = AuthActor(role=role, tenant_id=actor_tenant)  # type: ignore[arg-type]
    d = can_access(
        actor,
        "canonical:read",
        {"kind": "canonical_memory", "tenant_id": resource_tenant},
        skip_audit=True,
    )
    assert d.allow is expect


def test_cross_tenant_on_override_kind() -> None:
    actor = AuthActor(role="successor_strategist", tenant_id=T_A)
    d = can_access(actor, "override:submit", {"kind": "override", "tenant_id": T_B}, skip_audit=True)
    assert d.allow is False
    assert d.code == "forbidden"


@pytest.mark.parametrize("kind", ["canonical_memory", "override", "foia_export"])
def test_tenant_scoped_kind_without_tenant_id_raises_in_dev(kind: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "test")
    actor = AuthActor(role="platform_admin", tenant_id=T_A)
    with pytest.raises(TenantScopePolicyError):
        can_access(actor, "canonical:read", {"kind": kind}, skip_audit=True)  # type: ignore[typeddict-item]


def test_tenant_scoped_kind_without_tenant_id_denied_in_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")
    actor = AuthActor(role="deployment_strategist", tenant_id=T_A)
    d = can_access(actor, "canonical:read", {"kind": "canonical_memory"}, skip_audit=True)
    assert d.allow is False
    assert "tenant_id" in d.reason


@pytest.mark.parametrize(
    ("role", "action", "expect"),
    [
        ("platform_admin", "admin:read", True),
        ("customer_admin", "admin:read", True),
        ("deployment_strategist", "admin:read", False),
        ("fde", "admin:read", False),
        ("biz_dev", "admin:read", False),
        ("external_auditor", "admin:read", False),
        # demo_guest must never see /admin pages or /api/internal/v1 proxy routes.
        ("demo_guest", "admin:read", False),
        ("platform_admin", "internal:proxy", True),
        ("customer_admin", "internal:proxy", True),
        ("deployment_strategist", "internal:proxy", True),
        ("fde", "internal:proxy", True),
        ("biz_dev", "internal:proxy", False),
        ("successor_strategist", "internal:proxy", False),
        ("customer_records_officer", "internal:proxy", False),
        ("external_auditor", "internal:proxy", False),
        ("demo_guest", "internal:proxy", False),
    ],
)
def test_admin_and_internal_actions(role: str, action: str, expect: bool) -> None:
    assert matrix_allowed(role, action) is expect  # type: ignore[arg-type]
