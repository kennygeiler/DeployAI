"""SSRF guard for outbound MCP endpoints (pilot-refresh ticket A7).

One shared validator applied at BOTH ends of the endpoint lifecycle:

- **Config write** (``api/routes/tenant_mcp_configs_internal.py``) — reject
  obviously unsafe endpoints before they land in ``tenant_mcp_configs``.
- **Request time** (``agents/agent_kenny/mcp_client.py``) — re-resolve the
  hostname immediately before connecting so a DNS record that flipped to a
  private address after the config was written (DNS rebinding) is still
  caught.

Rules (default posture — no env flags set):

- Scheme must be ``https``. ``http`` is rejected outright.
- URLs carrying userinfo (``https://user:pass@host/``) are rejected — the
  userinfo trick is a classic way to spoof allow-list checks.
- The hostname must resolve, and every resolved address must be public:
  loopback, private (RFC 1918 / ULA ``fc00::/7`` incl. ``fd00::/8``),
  link-local (incl. the cloud metadata address ``169.254.169.254``),
  reserved, multicast, and unspecified addresses are all rejected.

Dev escape hatch: ``DEPLOYAI_MCP_ALLOW_INSECURE_LOCAL=1`` (default-off)
permits ``http`` for loopback hosts and skips the address-range rejection so
local compose stacks can point Kenny at ``http://localhost:9xxx`` MCP
servers. Never enable in production.

Env is read at call time (mirroring ``mcp_rate_limit``) so tests can flip
the flag with ``monkeypatch.setenv`` without a settings-cache dance.
"""

from __future__ import annotations

import ipaddress
import os
import socket
import urllib.parse
from collections.abc import Callable, Sequence

INSECURE_LOCAL_ENV = "DEPLOYAI_MCP_ALLOW_INSECURE_LOCAL"

# Resolver signature: hostname -> resolved IP address strings. Injectable so
# unit tests can simulate "public hostname resolving to a private IP" (the
# DNS-rebinding case) without touching real DNS.
Resolver = Callable[[str], Sequence[str]]

_LOOPBACK_HOSTNAMES = frozenset({"localhost"})


class EgressBlockedError(ValueError):
    """Endpoint failed SSRF validation. ``reason`` is a stable machine token
    (``scheme_not_https``, ``userinfo_present``, ``missing_host``,
    ``private_address``, ``dns_resolution_failed``, ``invalid_url``) so audit
    rows and API errors can carry it without string-parsing the message.
    """

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason


def _insecure_local_allowed() -> bool:
    return (os.environ.get(INSECURE_LOCAL_ENV) or "").strip().lower() in ("1", "true", "yes", "on")


def _default_resolver(host: str) -> Sequence[str]:
    """Resolve via ``getaddrinfo`` — returns every A/AAAA answer so one
    private record among several public ones still fails the check."""
    infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in infos]


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    # getaddrinfo may return zone-scoped IPv6 like "fe80::1%en0".
    candidate = value.split("%", 1)[0]
    try:
        return ipaddress.ip_address(candidate)
    except ValueError:
        return None


def _is_forbidden_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when the address must never be an outbound MCP target.

    ``is_private`` covers RFC 1918, loopback, link-local (incl. the cloud
    metadata address 169.254.169.254), and ULA ``fc00::/7`` (which contains
    ``fd00::/8``); the remaining checks are belt-and-braces for reserved,
    multicast, and unspecified ranges.
    """
    return bool(
        ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def _host_is_loopback_name(host: str) -> bool:
    if host.lower() in _LOOPBACK_HOSTNAMES:
        return True
    ip = _parse_ip(host)
    return ip is not None and ip.is_loopback


def validate_egress_endpoint(
    endpoint: str,
    *,
    resolver: Resolver | None = None,
    require_resolution: bool = True,
) -> None:
    """Validate one outbound MCP endpoint URL; raise :class:`EgressBlockedError`.

    ``require_resolution`` controls the DNS-failure posture:

    - ``True`` (request time): a hostname that does not resolve fails closed
      — we refuse to hand the URL to the HTTP client unverified.
    - ``False`` (config write): syntax + IP-literal checks are enforced, but
      an NXDOMAIN hostname is accepted; the endpoint simply won't work until
      DNS exists, at which point the request-time check re-validates it.
    """
    try:
        parsed = urllib.parse.urlsplit(endpoint.strip())
    except ValueError as exc:
        raise EgressBlockedError("invalid_url", f"endpoint is not a parseable URL: {exc}") from exc

    host = parsed.hostname
    if not host:
        raise EgressBlockedError("missing_host", "endpoint has no hostname")
    if parsed.username is not None or parsed.password is not None:
        raise EgressBlockedError(
            "userinfo_present",
            "endpoint must not carry userinfo (user:pass@host)",
        )

    dev_local = _insecure_local_allowed()
    if parsed.scheme != "https":
        if parsed.scheme == "http" and dev_local and _host_is_loopback_name(host):
            pass  # explicit dev opt-in: http to localhost only
        else:
            raise EgressBlockedError(
                "scheme_not_https",
                f"endpoint scheme must be https (got {parsed.scheme!r})",
            )

    if dev_local:
        # Dev flag skips the address-range rejection entirely (compose
        # stacks legitimately target 127.0.0.1 / 172.16.x service IPs).
        return

    literal = _parse_ip(host)
    if literal is not None:
        if _is_forbidden_ip(literal):
            raise EgressBlockedError(
                "private_address",
                f"endpoint address {literal} is in a forbidden range",
            )
        return

    resolve = resolver or _default_resolver
    try:
        addresses = list(resolve(host))
    except (OSError, socket.gaierror) as exc:
        if not require_resolution:
            return
        raise EgressBlockedError(
            "dns_resolution_failed",
            f"endpoint hostname {host!r} did not resolve: {exc}",
        ) from exc
    if not addresses:
        if not require_resolution:
            return
        raise EgressBlockedError(
            "dns_resolution_failed",
            f"endpoint hostname {host!r} resolved to no addresses",
        )
    for raw in addresses:
        ip = _parse_ip(str(raw))
        if ip is None:
            raise EgressBlockedError(
                "dns_resolution_failed",
                f"endpoint hostname {host!r} resolved to unparseable address {raw!r}",
            )
        if _is_forbidden_ip(ip):
            raise EgressBlockedError(
                "private_address",
                f"endpoint hostname {host!r} resolves to forbidden address {ip}",
            )


__all__ = [
    "INSECURE_LOCAL_ENV",
    "EgressBlockedError",
    "Resolver",
    "validate_egress_endpoint",
]
