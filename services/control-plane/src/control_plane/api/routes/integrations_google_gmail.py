"""Google Gmail OAuth (PKCE) + inbox → ``email.thread`` sync."""

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
from control_plane.auth.oidc_flow import pkce_pair
from control_plane.config.settings import get_settings
from control_plane.db import AppDbSession
from control_plane.domain.integrations.models import Integration
from control_plane.integrations.gmail_oauth import (
    build_gmail_authorization_url,
    exchange_gmail_code,
    gmail_oauth_creds,
)
from control_plane.services.gmail_sync import run_gmail_inbox_sync
from control_plane.services.ingestion_runs import (
    complete_ingestion_run_failure,
    complete_ingestion_run_success,
    start_ingestion_run,
)

_LOG = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/google-gmail", tags=["integrations-google-gmail"])

_C_STATE: Final = "dep_gmail_state"
_C_VERIFIER: Final = "dep_gmail_verifier"
_C_TENANT: Final = "dep_gmail_tenant"
_C_INTEGRATION: Final = "dep_gmail_integration"
_C_RETURN: Final = "dep_gmail_return"
_COOKIE_MAX: Final = 600
_C_PATH: Final = "/integrations/google-gmail"


def _https_redirect(redirect_uri: str) -> bool:
    return urllib.parse.urlparse(redirect_uri).scheme == "https"


def _safe_return(raw: str | None) -> str | None:
    if not raw or not str(raw).strip():
        return None
    s = str(raw).strip()
    if len(s) > 2048:
        return None
    p = urllib.parse.urlparse(s)
    if p.scheme not in ("http", "https") or not p.netloc:
        return None
    return s


@router.get("/connect", summary="Start Google Gmail OAuth (PKCE)", response_model=None)
async def google_gmail_connect(
    session: AppDbSession,
    actor: Annotated[AuthActor, Depends(bearer_auth_actor)],
    tenant_id: Annotated[uuid.UUID, Query(description="Account tenant to attach this integration to.")],
    return_to: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    c = gmail_oauth_creds(get_settings())
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set DEPLOYAI_GOOGLE_GMAIL_CLIENT_ID, _SECRET, and _REDIRECT_URI",
        )
    client_id, _sec, redir = c
    d = can_access(
        actor,
        "ingest:sync",
        {"kind": "tenant", "id": str(tenant_id)},
        skip_audit=False,
    )
    if not d.allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=d.reason)
    if actor.role != "platform_admin" and (actor.tenant_id is None or str(tenant_id) != actor.tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Token tenant does not match tenant_id")
    r = await session.execute(
        select(Integration).where(Integration.tenant_id == tenant_id, Integration.provider == "google_gmail").limit(1)
    )
    it = r.scalar_one_or_none()
    if it is None:
        it = Integration(
            tenant_id=tenant_id,
            provider="google_gmail",
            display_name="Gmail",
        )
        session.add(it)
        await session.flush()
    await session.commit()
    st = secrets.token_urlsafe(32)
    ver, chal = pkce_pair()
    loc = build_gmail_authorization_url(
        client_id=client_id,
        redirect_uri=redir,
        state=st,
        code_challenge=chal,
    )
    rdr = RedirectResponse(url=loc, status_code=status.HTTP_302_FOUND)
    secure = _https_redirect(redir)
    for name, v in [
        (_C_STATE, st),
        (_C_VERIFIER, ver),
        (_C_TENANT, str(tenant_id)),
        (_C_INTEGRATION, str(it.id)),
    ]:
        rdr.set_cookie(name, v, max_age=_COOKIE_MAX, httponly=True, samesite="lax", secure=secure, path=_C_PATH)
    ret = _safe_return(return_to)
    if ret:
        rdr.set_cookie(_C_RETURN, ret, max_age=_COOKIE_MAX, httponly=True, samesite="lax", secure=secure, path=_C_PATH)
    return rdr


@router.get("/callback", summary="Google redirects here after consent", response_model=None)
async def google_gmail_callback(
    request: Request,
    session: AppDbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> JSONResponse | RedirectResponse:
    c = gmail_oauth_creds(get_settings())
    if c is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Gmail OAuth is not configured")
    client_id, client_secret, redir = c
    if error:
        _LOG.info("gmail_oauth_error", extra={"err": error})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    st_c, ver, iid = (
        request.cookies.get(_C_STATE),
        request.cookies.get(_C_VERIFIER),
        request.cookies.get(_C_INTEGRATION),
    )
    if not code or not state or not st_c or not ver or not iid or state != st_c:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid OAuth state; restart connect in the same browser",
        )
    integ = await session.get(Integration, uuid.UUID(iid))
    if integ is None or integ.provider != "google_gmail":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration not found")
    async with httpx.AsyncClient() as h:
        toks = await exchange_gmail_code(
            h,
            code=code,
            redirect_uri=redir,
            client_id=client_id,
            client_secret=client_secret,
            code_verifier=ver,
        )
    ex_in = int(toks.get("expires_in") or 3600)
    at = str(toks.get("access_token") or "")
    rt = toks.get("refresh_token")
    if not at:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="token response missing access_token")
    if not isinstance(rt, str) or not rt:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No refresh_token (ensure prompt=consent and access_type=offline in Google console)",
        )
    prev = dict(integ.config) if isinstance(integ.config, dict) else {}
    integ.config = {
        **prev,
        "oauth": {
            "access_token": at,
            "refresh_token": rt,
            "expires_at_epoch": time.time() + ex_in,
            "token_type": str(toks.get("token_type") or "Bearer"),
        },
    }
    integ.state = "active"
    await session.commit()
    ret = request.cookies.get(_C_RETURN)
    if ret and str(ret).strip():
        rdr = RedirectResponse(url=str(ret), status_code=status.HTTP_302_FOUND)
        for n in (_C_STATE, _C_VERIFIER, _C_TENANT, _C_INTEGRATION, _C_RETURN):
            rdr.delete_cookie(n, path=_C_PATH)
        return rdr
    resp = JSONResponse(
        {
            "status": "connected",
            "integration_id": str(integ.id),
            "tenant_id": str(integ.tenant_id),
        }
    )
    for n in (_C_STATE, _C_VERIFIER, _C_TENANT, _C_INTEGRATION, _C_RETURN):
        resp.delete_cookie(n, path=_C_PATH)
    return resp


@router.post("/{integration_id}/sync", summary="Inbox list → email.thread (Gmail API)")
async def google_gmail_sync(
    integration_id: uuid.UUID,
    session: AppDbSession,
    actor: Annotated[AuthActor, Depends(bearer_auth_actor)],
) -> dict[str, object]:
    it = await session.get(Integration, integration_id)
    if it is None or it.provider != "google_gmail":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration not found")
    d = can_access(
        actor,
        "ingest:sync",
        {"kind": "tenant", "id": str(it.tenant_id)},
        skip_audit=False,
    )
    if not d.allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=d.reason)
    if actor.role != "platform_admin" and (actor.tenant_id is None or str(it.tenant_id) != actor.tenant_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Tenant mismatch")
    run_id = await start_ingestion_run(
        session,
        tenant_id=it.tenant_id,
        integration="google_gmail",
        meta={"integration_id": str(integration_id)},
    )
    try:
        out = await run_gmail_inbox_sync(session, it)
    except Exception as e:
        await complete_ingestion_run_failure(session, run_id, message=str(e))
        if isinstance(e, ValueError):
            await session.commit()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
        await session.commit()
        raise
    _meta: dict[str, object] = {"result": "gmail_inbox", "history_id": out.get("history_id")}
    await complete_ingestion_run_success(session, run_id, events_written=int(out.get("inserted", 0)), meta=_meta)
    await session.commit()
    return {"integration_id": str(integration_id), **out, "ingestion_run_id": str(run_id)}
