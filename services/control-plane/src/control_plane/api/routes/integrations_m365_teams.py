"""M365 / Teams meeting transcript OAuth + sync (Epic 3 Story 3-3, FR11)."""

from __future__ import annotations

import logging
import secrets
import time
import urllib.parse
import uuid
from typing import Annotated, Final

import httpx
from deployai_authz import AuthActor, can_access
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import select
from starlette.responses import JSONResponse, RedirectResponse

from control_plane.api.jwt_actor import bearer_auth_actor
from control_plane.auth.oidc_flow import OidcError
from control_plane.config.settings import get_settings
from control_plane.db import AppDbSession
from control_plane.domain.integrations.models import Integration
from control_plane.integrations.m365_oauth import (
    GRAPH_TEAMS_SCOPES,
    build_graph_delegate_authorization_url,
    exchange_delegation_code,
    fetch_metadata,
    m365_teams_oauth_creds,
    pkce_pair,
)
from control_plane.services.ingestion_runs import (
    complete_ingestion_run_failure,
    complete_ingestion_run_success,
    start_ingestion_run,
)
from control_plane.services.m365_teams_transcript_sync import run_teams_transcript_sync

_LOG = logging.getLogger(__name__)

router = APIRouter(prefix="/integrations/m365-teams", tags=["integrations-m365-teams"])

_C_STATE: Final = "dep_m365_state"
_C_VERIFIER: Final = "dep_m365_verifier"
_C_TENANT: Final = "dep_m365_tenant"
_C_INTEGRATION: Final = "dep_m365_integration"
_C_RETURN: Final = "dep_m365_return"
_COOKIE_MAX_AGE: Final = 600
_COOKIE_PATH: Final = "/integrations/m365-teams"


def _redirect_scheme_https(redirect_uri: str) -> bool:
    return urllib.parse.urlparse(redirect_uri).scheme == "https"


def _safe_return_to_url(raw: str | None) -> str | None:
    """Block open redirects: only allow http(s) with a host (no javascript:/data:)."""
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    if len(s) > 2048:
        return None
    p = urllib.parse.urlparse(s)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    return s


def _m365_teams_creds() -> tuple[str, str, str, str] | None:
    return m365_teams_oauth_creds(get_settings())


@router.get("/connect", summary="Start Microsoft 365 Teams transcript OAuth (Graph delegated)")
async def m365_teams_connect(
    session: AppDbSession,
    actor: Annotated[AuthActor, Depends(bearer_auth_actor)],
    tenant_id: Annotated[uuid.UUID, Query(description="Account tenant to attach this integration to.")],
    return_to: Annotated[
        str | None,
        Query(description="Optional URL to redirect to after /callback (https recommended)."),
    ] = None,
) -> RedirectResponse:
    c = _m365_teams_creds()
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "M365 Teams OAuth is not configured. Set DEPLOYAI_M365_TEAMS_REDIRECT_URI and OAuth clients; "
                "issuer/client may fall back to DEPLOYAI_OIDC_*."
            ),
        )
    issuer, client_id, _secret, m365_redir = c
    if not m365_redir or not m365_redir.strip():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DEPLOYAI_M365_TEAMS_REDIRECT_URI is required",
        )
    secure = _redirect_scheme_https(m365_redir)
    d = can_access(
        actor,
        "ingest:sync",
        {"kind": "tenant", "id": str(tenant_id)},
        skip_audit=False,
    )
    if not d.allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=d.reason)
    if actor.role != "platform_admin":
        if actor.tenant_id is None or str(tenant_id) != actor.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Token tenant does not match tenant_id",
            )

    r = await session.execute(
        select(Integration).where(Integration.tenant_id == tenant_id, Integration.provider == "m365_teams").limit(1)
    )
    it = r.scalar_one_or_none()
    if it is None:
        it = Integration(
            tenant_id=tenant_id,
            provider="m365_teams",
            display_name="Microsoft Teams (transcripts)",
        )
        session.add(it)
        await session.flush()
    await session.commit()

    st = secrets.token_urlsafe(32)
    code_verifier, code_challenge = pkce_pair()
    async with httpx.AsyncClient() as c_http:
        try:
            meta = await fetch_metadata(c_http, issuer)
        except OidcError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
        try:
            loc = build_graph_delegate_authorization_url(
                meta,
                client_id=client_id,
                redirect_uri=m365_redir,
                state=st,
                code_challenge=code_challenge,
                scope=GRAPH_TEAMS_SCOPES,
            )
        except Exception as e:  # pragma: no cover
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"build authorize URL: {e}",
            ) from e

    rdr = RedirectResponse(url=loc, status_code=status.HTTP_302_FOUND)
    cookies: list[tuple[str, str]] = [
        (_C_STATE, st),
        (_C_VERIFIER, code_verifier),
        (_C_TENANT, str(tenant_id)),
        (_C_INTEGRATION, str(it.id)),
    ]
    for name, val in cookies:
        rdr.set_cookie(
            name,
            val,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=secure,
            path=_COOKIE_PATH,
        )
    ret = _safe_return_to_url(return_to)
    if ret:
        rdr.set_cookie(
            _C_RETURN,
            ret,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            secure=secure,
            path=_COOKIE_PATH,
        )
    return rdr


@router.get(
    "/callback",
    summary="Microsoft redirects here after user consent (Teams)",
    response_model=None,
)
async def m365_teams_callback(
    request: Request,
    session: AppDbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> JSONResponse | RedirectResponse:
    c = _m365_teams_creds()
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="M365 Teams OAuth is not configured",
        )
    issuer, client_id, client_secret, m365_redir = c
    ck_state = request.cookies.get(_C_STATE)
    ck_ver = request.cookies.get(_C_VERIFIER)
    ck_iid = request.cookies.get(_C_INTEGRATION)
    if error:
        _LOG.info("m365_teams_oauth_error", extra={"error": error, "desc": (error_description or "")[:200]})
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": error, "error_description": error_description},
        )
    if not code or not state or not ck_state or not ck_ver or not ck_iid or state != ck_state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing or invalid OAuth state (retry connect from a fresh browser session)",
        )
    integ_id = uuid.UUID(ck_iid)
    r = await session.execute(select(Integration).where(Integration.id == integ_id).limit(1))
    it = r.scalar_one_or_none()
    if it is None or it.provider != "m365_teams":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration not found")

    async with httpx.AsyncClient() as c_http:
        try:
            meta = await fetch_metadata(c_http, issuer)
        except OidcError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
        try:
            toks = await exchange_delegation_code(
                c_http,
                str(meta["token_endpoint"]),
                code=code,
                redirect_uri=m365_redir,
                code_verifier=ck_ver,
                client_id=client_id,
                client_secret=client_secret,
            )
        except OidcError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    ex_in = int(toks.get("expires_in") or 3600)
    rt = toks.get("refresh_token")
    if not isinstance(rt, str) or not rt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="token response missing refresh_token; ensure admin consent and offline_access scope",
        )
    at = str(toks["access_token"])
    prev = dict(it.config) if isinstance(it.config, dict) else {}
    it.config = {
        **prev,
        "oauth": {
            "access_token": at,
            "refresh_token": rt,
            "expires_at_epoch": time.time() + ex_in,
            "token_type": str(toks.get("token_type") or "Bearer"),
        },
    }
    it.state = "active"
    await session.commit()

    ret = request.cookies.get(_C_RETURN)
    if ret and str(ret).strip():
        rdr = RedirectResponse(url=str(ret), status_code=status.HTTP_302_FOUND)
        for n in (_C_STATE, _C_VERIFIER, _C_TENANT, _C_INTEGRATION, _C_RETURN):
            rdr.delete_cookie(n, path=_COOKIE_PATH)
        return rdr

    resp = JSONResponse(
        {
            "status": "connected",
            "integration_id": str(it.id),
            "tenant_id": str(it.tenant_id),
        }
    )
    for n in (_C_STATE, _C_VERIFIER, _C_TENANT, _C_INTEGRATION, _C_RETURN):
        resp.delete_cookie(n, path=_COOKIE_PATH)
    return resp


@router.post("/{integration_id}/sync", summary="Calendar delta → online meeting transcripts (meeting.transcript)")
async def m365_teams_sync(
    integration_id: uuid.UUID,
    session: AppDbSession,
    actor: Annotated[AuthActor, Depends(bearer_auth_actor)],
) -> dict[str, object]:
    r = await session.execute(select(Integration).where(Integration.id == integration_id).limit(1))
    it = r.scalar_one_or_none()
    if it is None or it.provider != "m365_teams":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration not found")
    d = can_access(
        actor,
        "ingest:sync",
        {"kind": "tenant", "id": str(it.tenant_id)},
        skip_audit=False,
    )
    if not d.allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=d.reason)
    if actor.role != "platform_admin":
        if actor.tenant_id is None or str(it.tenant_id) != actor.tenant_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    run_id = await start_ingestion_run(
        session,
        tenant_id=it.tenant_id,
        integration="m365_teams",
        meta={"integration_id": str(integration_id)},
    )
    try:
        out = await run_teams_transcript_sync(session, it)
    except Exception as e:
        await complete_ingestion_run_failure(session, run_id, message=str(e))
        if isinstance(e, ValueError):
            await session.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
        await session.commit()
        raise
    _meta: dict[str, object] = {"result": "delta" if out.get("delta_link") else "same"}
    await complete_ingestion_run_success(session, run_id, events_written=int(out.get("inserted", 0)), meta=_meta)
    await session.commit()
    return {"integration_id": str(integration_id), **out, "ingestion_run_id": str(run_id)}
