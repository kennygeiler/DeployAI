"""Slack — OAuth v2 install, Events API, and ``slack.message`` → canonical (FR18)."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.parse
import uuid
from typing import Annotated, Final

import httpx
from deployai_authz import AuthActor, can_access
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import select
from starlette.responses import RedirectResponse

from control_plane.api.jwt_actor import bearer_auth_actor
from control_plane.config.settings import get_settings
from control_plane.db import AppDbSession
from control_plane.domain.integrations.models import Integration
from control_plane.integrations.slack_oauth import (
    build_slack_install_url,
    exchange_slack_oauth,
    slack_oauth_creds,
)
from control_plane.services.slack_event_ingest import process_slack_event_envelope

_LOG = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/slack", tags=["integrations-slack"])

_C_STATE: Final = "dep_slack_state"
_C_TENANT: Final = "dep_slack_tenant"
_C_INTEG: Final = "dep_slack_integration"
_C_RETURN: Final = "dep_slack_return"
_COOKIE_MAX: Final = 600
_C_PATH: Final = "/integrations/slack"


def _verify_slack_signature(*, body: bytes, timestamp: str, signature: str, secret: str) -> bool:
    if not secret or not signature.startswith("v0="):
        return False
    try:
        ts = int(timestamp)
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > 60 * 5:
        return False
    base = f"v0:{timestamp}:{body.decode('utf-8')}"
    dig = hmac.new(secret.encode("utf-8"), base.encode("utf-8"), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, f"v0={dig}")


def _https(redirect_uri: str) -> bool:
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


@router.get("/oauth/connect", summary="Slack app install (OAuth v2) for this tenant", response_model=None)
async def slack_oauth_connect(
    session: AppDbSession,
    actor: Annotated[AuthActor, Depends(bearer_auth_actor)],
    tenant_id: Annotated[uuid.UUID, Query(description="Account tenant to attach this workspace to.")],
    return_to: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    c = slack_oauth_creds(get_settings())
    if c is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Set DEPLOYAI_SLACK_CLIENT_ID, _SECRET, and _REDIRECT_URI",
        )
    cid, _s, redir = c
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
        select(Integration).where(Integration.tenant_id == tenant_id, Integration.provider == "slack").limit(1)
    )
    it = r.scalar_one_or_none()
    if it is None:
        it = Integration(tenant_id=tenant_id, provider="slack", display_name="Slack")
        session.add(it)
        await session.flush()
    await session.commit()
    st = secrets.token_urlsafe(32)
    loc = build_slack_install_url(client_id=cid, redirect_uri=redir, state=st)
    rdr = RedirectResponse(url=loc, status_code=status.HTTP_302_FOUND)
    sec = _https(redir)
    for name, v in [(_C_STATE, st), (_C_TENANT, str(tenant_id)), (_C_INTEG, str(it.id))]:
        rdr.set_cookie(name, v, max_age=_COOKIE_MAX, httponly=True, samesite="lax", secure=sec, path=_C_PATH)
    ret = _safe_return(return_to)
    if ret:
        rdr.set_cookie(_C_RETURN, ret, max_age=_COOKIE_MAX, httponly=True, samesite="lax", secure=sec, path=_C_PATH)
    return rdr


@router.get("/oauth/callback", summary="Slack redirect after app install", response_model=None)
async def slack_oauth_callback(
    request: Request,
    session: AppDbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> JSONResponse | RedirectResponse:
    c = slack_oauth_creds(get_settings())
    if c is None:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Slack OAuth is not configured")
    client_id, client_secret, redir = c
    st_c, iid = request.cookies.get(_C_STATE), request.cookies.get(_C_INTEG)
    if error:
        _LOG.info("slack_oauth_error", extra={"e": error})
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    if not code or not state or not st_c or not iid or state != st_c:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid OAuth state")
    it = await session.get(Integration, uuid.UUID(iid))
    if it is None or it.provider != "slack":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="integration not found")
    async with httpx.AsyncClient() as h:
        raw = await exchange_slack_oauth(
            h, code=code, client_id=client_id, client_secret=client_secret, redirect_uri=redir
        )
    tok = str(raw.get("access_token") or "")
    if not tok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="no bot token in OAuth response")
    team = raw.get("team")
    t_id, t_name = None, None
    if isinstance(team, dict):
        t_id = str(team.get("id") or "")
        t_name = str(team.get("name") or "")
    prev = dict(it.config) if isinstance(it.config, dict) else {}
    it.config = {
        **prev,
        "oauth": {
            "access_token": tok,
            "bot_user_id": str(raw.get("bot_user_id") or ""),
            "scope": str(raw.get("scope") or ""),
            "app_id": str(raw.get("app_id") or ""),
        },
        "slack": {"team_id": t_id, "team_name": t_name},
    }
    it.state = "active"
    await session.commit()
    ret = request.cookies.get(_C_RETURN)
    if ret and str(ret).strip():
        rdr = RedirectResponse(url=str(ret), status_code=status.HTTP_302_FOUND)
        for n in (_C_STATE, _C_TENANT, _C_INTEG, _C_RETURN):
            rdr.delete_cookie(n, path=_C_PATH)
        return rdr
    resp = JSONResponse(
        {
            "status": "connected",
            "integration_id": str(it.id),
            "tenant_id": str(it.tenant_id),
            "team_id": t_id,
        }
    )
    for n in (_C_STATE, _C_TENANT, _C_INTEG, _C_RETURN):
        resp.delete_cookie(n, path=_C_PATH)
    return resp


@router.post(
    "/events",
    summary="Slack Events API (URL challenge + event_callback → canonical)",
    response_model=None,
)
async def slack_events(
    request: Request,
    session: AppDbSession,
) -> JSONResponse | PlainTextResponse:
    body = await request.body()
    s = get_settings()
    secret = (s.slack_signing_secret or "").strip()
    sig = (request.headers.get("X-Slack-Signature") or "").strip()
    ts = (request.headers.get("X-Slack-Request-Timestamp") or "").strip()
    if secret and body:
        if not _verify_slack_signature(body=body, timestamp=ts, signature=sig, secret=secret):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid Slack signature",
            )
    if not body:
        raise HTTPException(status_code=400, detail="empty body")
    try:
        data = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail="JSON required") from e
    if not isinstance(data, dict):
        raise HTTPException(status_code=400, detail="expected object")
    et = str(data.get("type") or "")
    if et == "url_verification":
        ch = data.get("challenge")
        if isinstance(ch, str) and ch:
            return PlainTextResponse(content=ch, status_code=200, media_type="text/plain")
        return JSONResponse(content={"ok": False}, status_code=400)
    if et == "event_callback" and not secret:
        _LOG.warning("slack_events: signing secret unset; accepting event_callback (dev only)")
    if et == "event_callback":
        out = await process_slack_event_envelope(session, data=data)
        await session.commit()
        return JSONResponse(content={"ok": True, **out}, status_code=200)
    return JSONResponse(content={"ok": True, "note": f"ignored:{et}"}, status_code=200)
