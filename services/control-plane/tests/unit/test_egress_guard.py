"""Unit tests for the shared SSRF egress guard (ticket A7).

No network: every resolution path goes through an injected resolver. The
only exception is the IP-literal cases, which never resolve at all.
"""

from __future__ import annotations

import pytest

from control_plane.services.egress_guard import (
    INSECURE_LOCAL_ENV,
    EgressBlockedError,
    validate_egress_endpoint,
)

_PUBLIC_IP = "93.184.216.34"


def _resolver(*ips: str):
    return lambda host: list(ips)


def _failing_resolver(host: str):
    raise OSError(f"NXDOMAIN {host}")


@pytest.fixture(autouse=True)
def _no_dev_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(INSECURE_LOCAL_ENV, raising=False)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_https_public_host_passes() -> None:
    validate_egress_endpoint(
        "https://mcp.example.com/rpc",
        resolver=_resolver(_PUBLIC_IP),
    )


def test_https_public_ip_literal_passes() -> None:
    validate_egress_endpoint(f"https://{_PUBLIC_IP}/rpc")


# ---------------------------------------------------------------------------
# Scheme + URL shape
# ---------------------------------------------------------------------------


def test_http_rejected() -> None:
    with pytest.raises(EgressBlockedError) as e:
        validate_egress_endpoint("http://mcp.example.com/rpc", resolver=_resolver(_PUBLIC_IP))
    assert e.value.reason == "scheme_not_https"


def test_userinfo_rejected() -> None:
    with pytest.raises(EgressBlockedError) as e:
        validate_egress_endpoint("https://admin:hunter2@mcp.example.com/rpc", resolver=_resolver(_PUBLIC_IP))
    assert e.value.reason == "userinfo_present"


def test_missing_host_rejected() -> None:
    with pytest.raises(EgressBlockedError) as e:
        validate_egress_endpoint("https:///rpc")
    assert e.value.reason == "missing_host"


# ---------------------------------------------------------------------------
# Forbidden address ranges (IP literals)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://169.254.169.254/latest/meta-data",  # cloud metadata
        "https://10.1.2.3/rpc",  # RFC 1918
        "https://192.168.1.1/rpc",  # RFC 1918
        "https://127.0.0.1/rpc",  # loopback
        "https://[::1]/rpc",  # IPv6 loopback
        "https://[fd00::1]/rpc",  # IPv6 ULA (fd00::/8)
        "https://[fe80::1]/rpc",  # IPv6 link-local
        "https://0.0.0.0/rpc",  # unspecified
    ],
)
def test_forbidden_ip_literals_rejected(endpoint: str) -> None:
    with pytest.raises(EgressBlockedError) as e:
        validate_egress_endpoint(endpoint)
    assert e.value.reason == "private_address"


# ---------------------------------------------------------------------------
# Resolution (DNS-rebinding defense)
# ---------------------------------------------------------------------------


def test_hostname_resolving_to_private_ip_rejected() -> None:
    with pytest.raises(EgressBlockedError) as e:
        validate_egress_endpoint(
            "https://innocent-looking.example.com/rpc",
            resolver=_resolver("10.0.0.5"),
        )
    assert e.value.reason == "private_address"


def test_hostname_with_one_private_answer_among_public_rejected() -> None:
    with pytest.raises(EgressBlockedError) as e:
        validate_egress_endpoint(
            "https://mixed.example.com/rpc",
            resolver=_resolver(_PUBLIC_IP, "169.254.169.254"),
        )
    assert e.value.reason == "private_address"


def test_dns_failure_fails_closed_at_request_time() -> None:
    with pytest.raises(EgressBlockedError) as e:
        validate_egress_endpoint("https://nope.example.com/rpc", resolver=_failing_resolver)
    assert e.value.reason == "dns_resolution_failed"


def test_dns_failure_tolerated_at_config_write_time() -> None:
    """``require_resolution=False`` (config write): NXDOMAIN is accepted —
    the endpoint is useless but not dangerous; the request-time guard
    re-resolves before every call."""
    validate_egress_endpoint(
        "https://nope.example.com/rpc",
        resolver=_failing_resolver,
        require_resolution=False,
    )


def test_write_time_still_rejects_private_resolution() -> None:
    with pytest.raises(EgressBlockedError):
        validate_egress_endpoint(
            "https://sneaky.example.com/rpc",
            resolver=_resolver("192.168.0.10"),
            require_resolution=False,
        )


def test_write_time_still_rejects_ip_literal_and_scheme() -> None:
    with pytest.raises(EgressBlockedError):
        validate_egress_endpoint("https://10.0.0.1/rpc", require_resolution=False)
    with pytest.raises(EgressBlockedError):
        validate_egress_endpoint("http://mcp.example.com/rpc", resolver=_resolver(_PUBLIC_IP), require_resolution=False)


# ---------------------------------------------------------------------------
# Dev flag
# ---------------------------------------------------------------------------


def test_dev_flag_allows_http_localhost(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(INSECURE_LOCAL_ENV, "1")
    validate_egress_endpoint("http://localhost:9200/mcp")
    validate_egress_endpoint("http://127.0.0.1:9200/mcp")


def test_dev_flag_allows_private_ranges(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(INSECURE_LOCAL_ENV, "1")
    validate_egress_endpoint("https://10.1.2.3/rpc")


def test_dev_flag_does_not_allow_http_to_public_hosts(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(INSECURE_LOCAL_ENV, "1")
    with pytest.raises(EgressBlockedError) as e:
        validate_egress_endpoint("http://mcp.example.com/rpc", resolver=_resolver(_PUBLIC_IP))
    assert e.value.reason == "scheme_not_https"
