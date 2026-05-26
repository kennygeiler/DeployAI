"""Internal API — tenant MCP outbound configs (v2 Phase 5 Wave 2E).

Mounted under ``/internal/v1``. Requires ``X-DeployAI-Internal-Key``; the
``{tenant_id}`` path segment scopes every query.

Per scope-v2 §9.1 each row is one tenant-admin-curated external MCP
server (Slack / Linear / GDrive / Notion / GitHub) that Agent Kenny may
call. The runtime client (Wave 2D ``mcp_client.py``) loads the rows at
agent-loop start and merges the tool list into the registry. Wave 2F
adds the kill-switch + rate-limiter that consult the same rows.

This module is the **only** principal write path for the column shape:

- ``encrypted_auth_token`` is populated by :func:`encrypt_field` from
  ``deployai_tenancy.envelope`` (pgcrypto ``pgp_sym_encrypt_bytea`` under
  the tenant DEK). Raw tokens NEVER survive past the request boundary
  — :class:`TenantMcpConfigRead` exposes only ``has_auth_token: bool``.
- Every mutation emits a row onto ``ledger_events`` via
  :func:`emit_ledger_event`. The emitter's ``_scrub_secrets`` strips
  secret-shaped detail keys defensively (Wave 2E added ``auth_token`` to
  the needle list); routes here additionally take care not to put the
  token in ``detail`` at all.
- RLS is enforced via :func:`tenant_session` — the cached engine + the
  ``app.current_tenant`` GUC defended by the Wave 1A migration.

OAuth start/callback is wired end-to-end for Slack only; the other four
connectors return 501 until per-connector flows land in a follow-up
wave. State is held in a process-local in-memory dict (5-minute TTL) so
this PR does not need a fresh migration to add a new column. A TODO
flags the Wave 5+ persistence work.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import httpx
from deployai_tenancy import InMemoryDEKProvider
from deployai_tenancy.envelope import encrypt_field
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.api.routes.engagements_internal import require_internal
from control_plane.config.settings import get_settings
from control_plane.db import tenant_session
from control_plane.domain.mcp_outbound import (
    CONNECTOR_KINDS,
    ConnectorKind,
    TenantMcpConfig,
    TenantMcpConfigCreate,
    TenantMcpConfigRead,
    TenantMcpConfigUpdate,
)
from control_plane.integrations.slack_oauth import (
    SLACK_OAUTH_ACCESS,
    build_slack_install_url,
    exchange_slack_oauth,
)
from control_plane.ledger import emit_ledger_event

router = APIRouter(prefix="/tenants", tags=["internal-tenant-mcp-configs"])


# ---------------------------------------------------------------------------
# OAuth state — v1 in-memory store.
#
# TODO (Wave 5+): persist this on the row (new column ``oauth_state_token``
# + ``oauth_state_expires_at``) so a CP restart between ``oauth/start`` and
# ``oauth/callback`` does not invalidate every in-flight install. The
# in-memory map is acceptable for v1 because the round trip is interactive
# (browser bounce through Slack), seconds-scale, and the only consumer is
# the tenant admin who initiated the install.
# ---------------------------------------------------------------------------

_OAUTH_STATE_TTL = timedelta(minutes=10)
_oauth_state_store: dict[uuid.UUID, dict[str, Any]] = {}


def _oauth_state_put(config_id: uuid.UUID, *, state: str, redirect_uri: str) -> None:
    _oauth_state_store[config_id] = {
        "state": state,
        "redirect_uri": redirect_uri,
        "expires_at": datetime.now(UTC) + _OAUTH_STATE_TTL,
    }


def _oauth_state_consume(config_id: uuid.UUID, *, state: str) -> str:
    """Return the stored ``redirect_uri`` if ``state`` matches; raise 400 otherwise.

    Pops the entry on success so a second callback with the same state
    fails closed.
    """
    entry = _oauth_state_store.get(config_id)
    if entry is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no oauth state for this config — call /oauth/start first",
        )
    if entry["expires_at"] < datetime.now(UTC):
        _oauth_state_store.pop(config_id, None)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="oauth state expired — call /oauth/start again",
        )
    if not secrets.compare_digest(str(entry["state"]), state):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="oauth state mismatch",
        )
    _oauth_state_store.pop(config_id, None)
    return str(entry["redirect_uri"])


# ---------------------------------------------------------------------------
# Pydantic request shapes specific to this module.
# ---------------------------------------------------------------------------


class OAuthStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    redirect_uri: Annotated[str, Field(min_length=1, max_length=2000)]


class OAuthStartResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    authorization_url: str
    state: str


class OAuthCallbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: Annotated[str, Field(min_length=1, max_length=4000)]
    state: Annotated[str, Field(min_length=1, max_length=200)]


# ---------------------------------------------------------------------------
# Helpers.
# ---------------------------------------------------------------------------


async def _encrypt_token(session: AsyncSession, *, tenant_id: uuid.UUID, plaintext: str) -> bytes:
    """Encrypt a raw auth token via the tenant DEK.

    Uses :class:`InMemoryDEKProvider` for now (deterministic, dev/test
    scoped). Production swap to ``KMSEnvelopeDEKProvider`` is the same
    plumbing per ``services/_shared/tenancy/src/deployai_tenancy/envelope.py``.
    """
    provider = InMemoryDEKProvider()
    dek = await provider.get_dek(tenant_id)
    return await encrypt_field(session, plaintext=plaintext.encode("utf-8"), dek=dek)


async def _load_config(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    config_id: uuid.UUID,
) -> TenantMcpConfig:
    """Load a single mcp config row; 404 if missing or cross-tenant.

    The RLS policy + the ``tenant_id`` filter both fail-close — they're
    belt-and-braces. The cross-tenant case typically lands as RLS-filtered
    "not found" rather than a 403 because the row is invisible at the
    Postgres layer to the scoped session.
    """
    stmt = select(TenantMcpConfig).where(
        TenantMcpConfig.id == config_id,
        TenantMcpConfig.tenant_id == tenant_id,
    )
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="mcp config not found")
    return row


def _audit_detail(row: TenantMcpConfig, **extra: Any) -> dict[str, Any]:
    """Per-mutation ledger detail — connector + endpoint host only; no token."""
    detail: dict[str, Any] = {
        "connector_kind": row.connector_kind,
        "transport": row.transport,
        "endpoint": row.endpoint,
        "enabled": row.enabled,
        "name": row.name,
    }
    detail.update(extra)
    return detail


def _validate_connector(connector_kind: str) -> None:
    if connector_kind not in CONNECTOR_KINDS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"invalid connector_kind: {connector_kind}",
        )


# ---------------------------------------------------------------------------
# CRUD.
# ---------------------------------------------------------------------------


@router.get(
    "/{tenant_id}/mcp_configs",
    response_model=list[TenantMcpConfigRead],
    dependencies=[Depends(require_internal)],
)
async def list_mcp_configs(tenant_id: uuid.UUID) -> list[TenantMcpConfigRead]:
    async with tenant_session(tenant_id) as session:
        result = await session.execute(
            select(TenantMcpConfig)
            .where(TenantMcpConfig.tenant_id == tenant_id)
            .order_by(TenantMcpConfig.created_at.asc())
        )
        rows = list(result.scalars().all())
    return [TenantMcpConfigRead.from_orm_row(r) for r in rows]


@router.post(
    "/{tenant_id}/mcp_configs",
    response_model=TenantMcpConfigRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal)],
)
async def create_mcp_config(
    tenant_id: uuid.UUID,
    body: TenantMcpConfigCreate,
) -> TenantMcpConfigRead:
    # Pydantic already constrains ``connector_kind`` to the Literal, but
    # re-validate so a string fuzz / future widening surfaces as 422 here
    # instead of a 500 from the DB CHECK.
    _validate_connector(body.connector_kind)

    async with tenant_session(tenant_id) as session:
        row = TenantMcpConfig(
            tenant_id=tenant_id,
            name=body.name,
            connector_kind=body.connector_kind,
            transport=body.transport,
            endpoint=body.endpoint,
            allowed_tools=list(body.allowed_tools) if body.allowed_tools is not None else None,
            enabled=body.enabled,
        )
        if body.auth_token is not None:
            row.encrypted_auth_token = await _encrypt_token(
                session,
                tenant_id=tenant_id,
                plaintext=body.auth_token,
            )
        session.add(row)
        try:
            await session.flush()
        except IntegrityError as exc:
            # uq_tenant_mcp_configs_tenant_id_name
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"mcp config name already exists for tenant: {body.name}",
            ) from exc
        await session.refresh(row)

        await emit_ledger_event(
            session,
            tenant_id=tenant_id,
            engagement_id=None,
            occurred_at=datetime.now(UTC),
            actor_kind="user",
            actor_id=None,
            source_kind="mcp_config_created",
            source_ref=row.id,
            summary=f"mcp config created: {row.name} ({row.connector_kind})"[:500],
            detail=_audit_detail(row, has_auth_token=row.encrypted_auth_token is not None),
        )
        snapshot = TenantMcpConfigRead.from_orm_row(row)
    return snapshot


@router.get(
    "/{tenant_id}/mcp_configs/{config_id}",
    response_model=TenantMcpConfigRead,
    dependencies=[Depends(require_internal)],
)
async def get_mcp_config(tenant_id: uuid.UUID, config_id: uuid.UUID) -> TenantMcpConfigRead:
    async with tenant_session(tenant_id) as session:
        row = await _load_config(session, tenant_id=tenant_id, config_id=config_id)
        return TenantMcpConfigRead.from_orm_row(row)


@router.patch(
    "/{tenant_id}/mcp_configs/{config_id}",
    response_model=TenantMcpConfigRead,
    dependencies=[Depends(require_internal)],
)
async def update_mcp_config(
    tenant_id: uuid.UUID,
    config_id: uuid.UUID,
    body: TenantMcpConfigUpdate,
) -> TenantMcpConfigRead:
    fields = body.model_dump(exclude_unset=True)
    async with tenant_session(tenant_id) as session:
        row = await _load_config(session, tenant_id=tenant_id, config_id=config_id)

        token_rotated = False
        if "name" in fields and body.name is not None:
            row.name = body.name
        if "endpoint" in fields and body.endpoint is not None:
            row.endpoint = body.endpoint
        if "transport" in fields and body.transport is not None:
            row.transport = body.transport
        if "allowed_tools" in fields:
            row.allowed_tools = list(body.allowed_tools) if body.allowed_tools is not None else None
        if "enabled" in fields and body.enabled is not None:
            row.enabled = body.enabled
        if "auth_token" in fields and body.auth_token is not None:
            row.encrypted_auth_token = await _encrypt_token(
                session,
                tenant_id=tenant_id,
                plaintext=body.auth_token,
            )
            token_rotated = True
        row.updated_at = datetime.now(UTC)
        try:
            await session.flush()
        except IntegrityError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="mcp config update conflicts with an existing row",
            ) from exc
        await session.refresh(row)

        await emit_ledger_event(
            session,
            tenant_id=tenant_id,
            engagement_id=None,
            occurred_at=datetime.now(UTC),
            actor_kind="user",
            actor_id=None,
            source_kind="mcp_config_updated",
            source_ref=row.id,
            summary=f"mcp config updated: {row.name} ({row.connector_kind})"[:500],
            detail=_audit_detail(
                row,
                changed_fields=sorted(fields.keys() - {"auth_token"}),
                token_rotated=token_rotated,
            ),
        )
        if token_rotated:
            await emit_ledger_event(
                session,
                tenant_id=tenant_id,
                engagement_id=None,
                occurred_at=datetime.now(UTC),
                actor_kind="user",
                actor_id=None,
                source_kind="mcp_oauth_token_rotated",
                source_ref=row.id,
                summary=f"mcp oauth token rotated: {row.name} ({row.connector_kind})"[:500],
                detail=_audit_detail(row, rotation_origin="patch"),
            )
        snapshot = TenantMcpConfigRead.from_orm_row(row)
    return snapshot


@router.delete(
    "/{tenant_id}/mcp_configs/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal)],
)
async def delete_mcp_config(tenant_id: uuid.UUID, config_id: uuid.UUID) -> None:
    async with tenant_session(tenant_id) as session:
        row = await _load_config(session, tenant_id=tenant_id, config_id=config_id)
        # Snapshot identity / metadata for the audit event before we drop
        # the row — once it's gone we can't read its fields.
        snapshot = _audit_detail(row)
        row_id = row.id
        row_name = row.name
        row_connector = row.connector_kind
        await session.delete(row)
        await session.flush()
        await emit_ledger_event(
            session,
            tenant_id=tenant_id,
            engagement_id=None,
            occurred_at=datetime.now(UTC),
            actor_kind="user",
            actor_id=None,
            source_kind="mcp_config_deleted",
            source_ref=row_id,
            summary=f"mcp config deleted: {row_name} ({row_connector})"[:500],
            detail=snapshot,
        )
    return None


# ---------------------------------------------------------------------------
# OAuth start / callback.
# ---------------------------------------------------------------------------


_OAUTH_NOT_IMPLEMENTED = {
    "linear": "Linear OAuth flow not yet wired — Wave 5+",
    "gdrive": "GDrive OAuth flow not yet wired — Wave 5+",
    "notion": "Notion OAuth flow not yet wired — Wave 5+",
    "github": "GitHub OAuth flow not yet wired — Wave 5+",
}


def _connector_unsupported(connector_kind: str) -> str | None:
    return _OAUTH_NOT_IMPLEMENTED.get(connector_kind)


@router.post(
    "/{tenant_id}/mcp_configs/{config_id}/oauth/start",
    response_model=OAuthStartResponse,
    dependencies=[Depends(require_internal)],
)
async def oauth_start(
    tenant_id: uuid.UUID,
    config_id: uuid.UUID,
    body: OAuthStartRequest,
) -> OAuthStartResponse:
    async with tenant_session(tenant_id) as session:
        row = await _load_config(session, tenant_id=tenant_id, config_id=config_id)
        connector: ConnectorKind = row.connector_kind  # type: ignore[assignment]

    unsupported = _connector_unsupported(connector)
    if unsupported is not None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=unsupported,
        )
    if connector != "slack":
        # Defensive — every non-slack connector should be in the
        # unsupported map. Falling through here would mean a new
        # connector was added to the catalog without an OAuth branch.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"OAuth flow not yet wired for connector: {connector}",
        )

    settings = get_settings()
    client_id = (settings.slack_client_id or "").strip()
    if not client_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack OAuth is not configured — set DEPLOYAI_SLACK_CLIENT_ID",
        )

    state = secrets.token_urlsafe(32)
    _oauth_state_put(config_id, state=state, redirect_uri=body.redirect_uri)
    url = build_slack_install_url(
        client_id=client_id,
        redirect_uri=body.redirect_uri,
        state=state,
    )
    return OAuthStartResponse(authorization_url=url, state=state)


@router.post(
    "/{tenant_id}/mcp_configs/{config_id}/oauth/callback",
    response_model=TenantMcpConfigRead,
    dependencies=[Depends(require_internal)],
)
async def oauth_callback(
    tenant_id: uuid.UUID,
    config_id: uuid.UUID,
    body: OAuthCallbackRequest,
) -> TenantMcpConfigRead:
    async with tenant_session(tenant_id) as session:
        row = await _load_config(session, tenant_id=tenant_id, config_id=config_id)
        connector: ConnectorKind = row.connector_kind  # type: ignore[assignment]

    unsupported = _connector_unsupported(connector)
    if unsupported is not None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=unsupported,
        )
    if connector != "slack":
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"OAuth flow not yet wired for connector: {connector}",
        )

    settings = get_settings()
    client_id = (settings.slack_client_id or "").strip()
    client_secret = (settings.slack_client_secret or "").strip()
    if not (client_id and client_secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Slack OAuth is not configured — set DEPLOYAI_SLACK_CLIENT_ID and _SECRET",
        )

    redirect_uri = _oauth_state_consume(config_id, state=body.state)

    async with httpx.AsyncClient() as client:
        try:
            data = await exchange_slack_oauth(
                client,
                code=body.code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Slack OAuth exchange failed: {exc}",
            ) from exc

    # Slack returns the bot user's token under ``access_token`` (or
    # nested under ``access_token`` in newer payloads). Treat the access
    # token as the auth token Kenny presents to the MCP server.
    token = data.get("access_token")
    if not isinstance(token, str) or not token:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=(f"Slack OAuth response missing access_token (payload keys: {sorted(data.keys())})"),
        )

    async with tenant_session(tenant_id) as session:
        row = await _load_config(session, tenant_id=tenant_id, config_id=config_id)
        row.encrypted_auth_token = await _encrypt_token(
            session,
            tenant_id=tenant_id,
            plaintext=token,
        )
        row.updated_at = datetime.now(UTC)
        await session.flush()
        await session.refresh(row)
        await emit_ledger_event(
            session,
            tenant_id=tenant_id,
            engagement_id=None,
            occurred_at=datetime.now(UTC),
            actor_kind="user",
            actor_id=None,
            source_kind="mcp_oauth_token_rotated",
            source_ref=row.id,
            summary=f"mcp oauth token rotated via callback: {row.name} ({row.connector_kind})"[:500],
            detail=_audit_detail(
                row,
                rotation_origin="oauth_callback",
                oauth_endpoint=SLACK_OAUTH_ACCESS,
            ),
        )
        snapshot = TenantMcpConfigRead.from_orm_row(row)
    return snapshot


__all__ = ["router"]
