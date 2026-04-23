"""Exception hierarchy is stable and catchable."""

from __future__ import annotations

import pytest

from deployai_tenancy.errors import (
    DEKUnavailable,
    IsolationViolation,
    MissingTenantScope,
    TenancyError,
)


@pytest.mark.parametrize(
    "exc_cls",
    [MissingTenantScope, IsolationViolation, DEKUnavailable],
)
def test_all_subclass_tenancy_error(exc_cls: type[TenancyError]) -> None:
    assert issubclass(exc_cls, TenancyError)


def test_missing_scope_distinct_from_isolation_violation() -> None:
    assert not issubclass(MissingTenantScope, IsolationViolation)
    assert not issubclass(IsolationViolation, MissingTenantScope)


def test_caught_by_base_class() -> None:
    with pytest.raises(TenancyError):
        raise MissingTenantScope("x")
    with pytest.raises(TenancyError):
        raise IsolationViolation("x")
    with pytest.raises(TenancyError):
        raise DEKUnavailable("x")
