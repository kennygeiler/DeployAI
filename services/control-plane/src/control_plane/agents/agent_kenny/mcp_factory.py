"""Process-wide singletons for outbound MCP (Wave 3G — Phase 5 keystone).

The agent loop needs *one* :class:`McpOutboundClient`, *one*
:class:`McpKillSwitch`, and *one* :class:`InMemoryMcpRateLimiter` per
process so the in-memory caches (kill-switch TTL, per-turn counters,
per-tenant per-tool sliding windows) stay coherent across requests. The
FastAPI ``_lifespan`` constructs them once at app boot and stashes them
on ``app.state`` for the route layer to read; tests can monkeypatch the
module-level globals or pass their own doubles directly to the
``KennyAgentService`` constructor.

This module is the *only* place those singletons live. Other modules
must call :func:`get_mcp_kill_switch`, :func:`get_mcp_rate_limiter`, or
:func:`build_mcp_outbound_client` — never construct
:class:`McpOutboundClient` directly. This keeps the secret-key flow
(threat-model §3.4.1 — token never leaves the client) and the
rate-limit accounting one-process consistent.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import httpx
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
)

from control_plane.agents.agent_kenny.mcp_client import (
    AuditSessionFactory,
    DekResolver,
    McpOutboundClient,
    make_audit_session_factory,
)
from control_plane.agents.agent_kenny.mcp_kill_switch import DbMcpKillSwitch
from control_plane.agents.agent_kenny.mcp_rate_limit import InMemoryMcpRateLimiter

if TYPE_CHECKING:
    from control_plane.agents.agent_kenny.embeddings.voyage_client import VoyageEmbedder
    from control_plane.agents.agent_kenny.mcp_client import (
        McpKillSwitch,
        McpRateLimiter,
    )

_log = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Module-level singletons. ``None`` until first call.
# Resetting them is for tests only — :func:`reset_for_tests`.
# --------------------------------------------------------------------------

_kill_switch: DbMcpKillSwitch | None = None
_rate_limiter: InMemoryMcpRateLimiter | None = None


def get_mcp_kill_switch(
    session_factory: async_sessionmaker[AsyncSession],
) -> McpKillSwitch:
    """Return the process-wide :class:`DbMcpKillSwitch` singleton.

    Lazy-constructed on first call so the engine + session factory the
    rest of the app uses is already wired. The ``session_factory``
    argument is only used on the first call — subsequent calls return
    the cached instance regardless of what factory is passed (asserting
    on this would only annoy callers that legitimately rebuild a factory
    in tests).
    """
    global _kill_switch
    if _kill_switch is None:
        _kill_switch = DbMcpKillSwitch(session_factory)
    return _kill_switch


def get_mcp_rate_limiter() -> McpRateLimiter:
    """Return the process-wide :class:`InMemoryMcpRateLimiter` singleton.

    Caps come from env at first-call time (see :mod:`mcp_rate_limit`):

    - ``DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_TURN`` (default 10)
    - ``DEPLOYAI_MCP_OUTBOUND_TOOL_CALLS_PER_MINUTE`` (default 60)
    """
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = InMemoryMcpRateLimiter()
    return _rate_limiter


def build_mcp_outbound_client(
    *,
    http_client: httpx.AsyncClient,
    session_factory: async_sessionmaker[AsyncSession],
    engine: AsyncEngine,
    dek_resolver: DekResolver | None = None,
) -> McpOutboundClient:
    """Construct an :class:`McpOutboundClient` with the process singletons.

    Wave 3G's only consumer is the FastAPI lifespan; tests typically
    bypass this and construct :class:`McpOutboundClient` directly with
    mocked transports. The ``dek_resolver`` defaults to the production
    ``deployai_tenancy.envelope.decrypt_field`` wrapper — passed in
    explicitly only when a test wants a passthrough.
    """
    kill_switch = get_mcp_kill_switch(session_factory)
    rate_limiter = get_mcp_rate_limiter()
    audit_session: AuditSessionFactory = make_audit_session_factory(engine=engine)
    resolver = dek_resolver if dek_resolver is not None else _default_dek_resolver(session_factory)
    return McpOutboundClient(
        http_client=http_client,
        dek_resolver=resolver,
        rate_limiter=rate_limiter,
        kill_switch=kill_switch,
        audit_session_factory=audit_session,
    )


def _default_dek_resolver(session_factory: async_sessionmaker[AsyncSession]) -> DekResolver:
    """Wrap ``deployai_tenancy.envelope.decrypt_field`` as an async closure.

    Lazy import keeps the module import-time graph free of a hard
    dependency on ``deployai_tenancy`` for callers that pass their own
    resolver (every unit test). The resolver opens a fresh tenant-scoped
    session so ``requires_tenant_scope`` is satisfied; the DEK itself is
    sourced from :class:`InMemoryDEKProvider` and is never returned to
    the caller — only the decrypted plaintext (the OAuth bearer) is.
    """
    from deployai_tenancy import TenantScopedSession  # local import
    from deployai_tenancy.envelope import (
        InMemoryDEKProvider,
        decrypt_field,
    )

    provider = InMemoryDEKProvider()
    # ``session_factory`` is held so the resolver closure can fetch the
    # underlying engine if a future implementation needs it. The current
    # production path uses ``TenantScopedSession`` against the same
    # engine the factory wraps.
    del session_factory  # unused for now; kept on signature for future-proofing

    async def resolver(tenant_id: Any, ciphertext: bytes) -> str:
        from control_plane.db import get_engine

        engine = get_engine()
        dek = await provider.get_dek(tenant_id)
        async with TenantScopedSession(tenant_id=tenant_id, engine=engine) as session:
            plaintext_bytes = await decrypt_field(
                session,
                ciphertext=ciphertext,
                dek=dek,
            )
        return plaintext_bytes.decode("utf-8")

    return resolver


# --------------------------------------------------------------------------
# Lifespan helpers (called from main.py's ``_lifespan``)
# --------------------------------------------------------------------------


def install_on_app_state(app: Any, *, engine: AsyncEngine) -> None:
    """Stash the singletons + a shared ``httpx.AsyncClient`` on ``app.state``.

    Mirrors the pattern Story 1.7 set for the OTel + DB statement listener.
    Routes pull the client via ``request.app.state.mcp_outbound_client``
    (a thin Depends would also work; both end up at the same instance).

    The ``httpx.AsyncClient`` carries a connection pool + TLS config so
    we don't reopen sockets per call. Closed in :func:`shutdown_on_app_state`.

    Phase 5.5 Wave C: also installs ``app.state.embedder`` so
    ``KennyAgentService`` can pull the Voyage client without a per-
    request rebuild. The Wave C placeholder resolves to ``None`` until
    Wave B's :class:`VoyageClient` lands; the agent loop already
    tolerates a missing embedder by surfacing an is_error tool_result
    for ``vector_search`` calls.
    """
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    http_client = httpx.AsyncClient()
    client = build_mcp_outbound_client(
        http_client=http_client,
        session_factory=session_factory,
        engine=engine,
    )
    app.state.mcp_outbound_client = client
    app.state.mcp_outbound_http = http_client
    app.state.mcp_kill_switch = get_mcp_kill_switch(session_factory)
    app.state.mcp_rate_limiter = get_mcp_rate_limiter()
    app.state.embedder = _build_default_embedder()


def _build_default_embedder() -> VoyageEmbedder | None:
    """Construct the process-wide :class:`VoyageEmbedder` if Wave B is wired.

    Wave B (the real Voyage client) lands the concrete
    ``VoyageClient`` implementation. Until then, this returns ``None``
    so ``vector_search`` falls back gracefully; once Wave B merges, this
    helper switches to ``return VoyageClient.from_env()``.

    Kept as a thin seam (rather than inlined) so the Wave B PR is a
    one-line edit + so tests can monkeypatch this single symbol when
    they need a stub embedder injected at lifespan time.
    """
    try:
        # Wave B will add ``VoyageClient`` alongside the existing
        # protocol. Importing it lazily keeps Wave C's tests happy
        # without a hard dependency on Wave B's modules.
        from control_plane.agents.agent_kenny.embeddings.voyage_client import (
            VoyageClient,  # type: ignore[attr-defined]
        )
    except ImportError:
        return None
    try:
        return VoyageClient.from_env()  # type: ignore[no-any-return]
    except Exception:  # pragma: no cover — defensive, Wave B owns the constructor
        _log.exception("VoyageClient.from_env failed; vector_search will be unavailable")
        return None


async def shutdown_on_app_state(app: Any) -> None:
    """Close the shared :class:`httpx.AsyncClient` so the pool releases sockets."""
    http_client = getattr(app.state, "mcp_outbound_http", None)
    if http_client is not None:
        try:
            await http_client.aclose()
        except Exception:
            # Lifespan teardown must never crash the shutdown sequence.
            _log.exception("mcp_outbound http client close failed")


def reset_for_tests() -> None:
    """Forget the cached singletons. **Tests only**.

    The kill switch + rate limiter carry per-process caches; integration
    tests that swap the engine mid-suite must call this to avoid the
    old engine's sessionmaker being held alive in the kill-switch cache.
    """
    global _kill_switch, _rate_limiter
    _kill_switch = None
    _rate_limiter = None


__all__ = [
    "build_mcp_outbound_client",
    "get_mcp_kill_switch",
    "get_mcp_rate_limiter",
    "install_on_app_state",
    "reset_for_tests",
    "shutdown_on_app_state",
]
