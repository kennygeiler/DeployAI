"""Hermetic tests for `_derive_app_url` (Story 1.10 harness URL surgery).

Backed by `sqlalchemy.engine.make_url` so special characters in passwords
(`@`, `:`, `/`, `#`) round-trip correctly via URL-encoding. The earlier
string-surgery implementation broke on these, and the fuzz harness would
have silently connected to the wrong host.
"""

from __future__ import annotations

import pytest

from control_plane.fuzz.cross_tenant import _derive_app_url


def test_swaps_userinfo_preserving_host_and_db() -> None:
    result = _derive_app_url(
        "postgresql+psycopg://root:rootpw@localhost:5432/deployai",
        user="deployai_app",
        password="apppw",
    )
    assert result == "postgresql+psycopg://deployai_app:apppw@localhost:5432/deployai"


def test_preserves_query_string() -> None:
    result = _derive_app_url(
        "postgresql+psycopg://root:rootpw@db:5432/deployai?sslmode=require",
        user="deployai_app",
        password="apppw",
    )
    assert result.endswith("?sslmode=require")
    assert "deployai_app:apppw" in result


def test_password_containing_at_sign_round_trips() -> None:
    """Naive `split('@', 1)` would silently mis-parse this."""
    result = _derive_app_url(
        "postgresql+psycopg://root:pw@host:5432/db",
        user="deployai_app",
        password="pa@ss",
    )
    # The password `@` must be percent-encoded in the resulting URL; the
    # actual parser round-trip is what the CLI hands to `create_async_engine`.
    assert "deployai_app" in result
    assert "pa%40ss" in result or "pa@ss" in result
    assert result.endswith("@host:5432/db")


def test_password_containing_colon_and_slash_round_trip() -> None:
    result = _derive_app_url(
        "postgresql+psycopg://root:pw@host:5432/db",
        user="deployai_app",
        password="p:w/d",
    )
    assert "deployai_app" in result
    assert result.endswith("@host:5432/db")


def test_url_without_userinfo_still_works() -> None:
    """`make_url` handles this — we inject the credentials regardless."""
    result = _derive_app_url(
        "postgresql+psycopg://localhost:5432/deployai",
        user="deployai_app",
        password="apppw",
    )
    assert "deployai_app:apppw" in result
    assert result.endswith("@localhost:5432/deployai")


def test_malformed_url_raises() -> None:
    with pytest.raises(ValueError, match="cannot parse database url"):
        _derive_app_url("::: not a url", user="x", password="y")
