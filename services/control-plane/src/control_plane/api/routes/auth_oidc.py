"""OIDC sign-in (Story 2-2) — Entra v2.0 with PKCE, JIT user, Redis session, cookies."""

from __future__ import annotations

import secrets
import urllib.parse
import uuid
from typing import Annotated, Final

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from starlette.responses import RedirectResponse

from control_plane.auth.oidc_flow import (
    OidcError,
    build_authorization_url,
    create_jwk_client,
    exchange_code_for_tokens,
    fetch_openid_metadata,
    pkce_pair,
    verify_id_token,
)
from control_plane.auth.session_service import issue_tokens
from control_plane.config.settings import get_settings
from control_plane.db import AppDbSession
from control_plane.services.oidc_user import resolve_or_create_oidc_user

_C_STATE: Final = "dep_oidc_state"
_C_VERIFIER: Final = "dep_oidc_verifier"
_C_NONCE: Final = "dep_oidc_nonce"
_COOKIE_MAX_AGE: Final = 600

oidc_router = APIRouter(prefix="/auth/oidc", tags=["auth-oidc"])
auth_entry_router = APIRouter(prefix="/auth", tags=["auth"])


def _oidc_fully_configured() -> bool:
    s = get_settings()
    return bool(
        s.oidc_issuer
        and s.oidc_issuer.strip()
        and s.oidc_client_id
        and s.oidc_client_id.strip()
        and s.oidc_client_secret
        and s.oidc_client_secret.strip()
        and s.oidc_redirect_uri
        and s.oidc_redirect_uri.strip()
    )


def _redirect_scheme_https(redirect_uri: str) -> bool:
    return urllib.parse.urlparse(redirect_uri).scheme == "https"


class OidcSessionIssued(BaseModel):
    sub: str
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    email: str | None = None
    name: str | None = None
    message: str = Field(
        default="Session stored in Redis; HttpOnly dep_access / dep_refresh cookies set (same-site).",
    )


@oidc_router.get("/login", summary="Start OIDC + PKCE sign-in (redirects to Microsoft Entra)")
async def oidc_login() -> Response:
    if not _oidc_fully_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured (set DEPLOYAI_OIDC_ISSUER, CLIENT_ID, CLIENT_SECRET, REDIRECT_URI).",
        )
    s = get_settings()
    assert s.oidc_issuer and s.oidc_client_id and s.oidc_client_secret and s.oidc_redirect_uri
    state = secrets.token_urlsafe(32)
    code_verifier, code_challenge = pkce_pair()
    nonce = secrets.token_urlsafe(16)
    secure = _redirect_scheme_https(s.oidc_redirect_uri)

    async with httpx.AsyncClient() as c:
        try:
            metadata = await fetch_openid_metadata(c, s.oidc_issuer)
        except OidcError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
        try:
            loc = build_authorization_url(
                metadata=metadata,
                client_id=s.oidc_client_id,
                redirect_uri=s.oidc_redirect_uri,
                state=state,
                code_challenge=code_challenge,
                nonce=nonce,
            )
        except Exception as e:  # pragma: no cover
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="failed to build authorize URL"
            ) from e

    resp = RedirectResponse(url=loc, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    for key, value in (
        (_C_STATE, state),
        (_C_VERIFIER, code_verifier),
        (_C_NONCE, nonce),
    ):
        resp.set_cookie(
            key,
            value=value,
            max_age=_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
            path="/",
            secure=secure,
        )
    return resp


@oidc_router.get(
    "/callback",
    response_model=OidcSessionIssued,
    summary="OIDC callback: code + id_token verify, JIT user, issue Redis session, Set-Cookie",
)
async def oidc_callback(
    request: Request,
    response: Response,
    session: AppDbSession,
    code: Annotated[str | None, Query()] = None,
    state: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
) -> OidcSessionIssued:
    if error or error_description:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error or error_description or "IdP error",
        )
    if not _oidc_fully_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC is not configured.",
        )
    if not code or not state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing code or state",
        )
    c_state = request.cookies.get(_C_STATE)
    c_ver = request.cookies.get(_C_VERIFIER)
    c_nonce = request.cookies.get(_C_NONCE)
    if not c_state or not c_ver or not c_nonce or c_state != state:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or missing OIDC state (retry login)",
        )
    sett = get_settings()
    assert sett.oidc_issuer and sett.oidc_client_id and sett.oidc_client_secret and sett.oidc_redirect_uri
    secure = _redirect_scheme_https(sett.oidc_redirect_uri)

    async with httpx.AsyncClient() as c:
        try:
            metadata = await fetch_openid_metadata(c, sett.oidc_issuer)
        except OidcError as e:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(e)) from e
        try:
            token_blob = await exchange_code_for_tokens(
                c,
                metadata,
                code=code,
                redirect_uri=sett.oidc_redirect_uri,
                code_verifier=c_ver,
                client_id=sett.oidc_client_id,
                client_secret=sett.oidc_client_secret,
            )
        except OidcError as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    id_tok = str(token_blob["id_token"])
    jwk = create_jwk_client(metadata)
    try:
        claims = verify_id_token(
            id_tok,
            metadata,
            client_id=sett.oidc_client_id,
            jwk_client=jwk,
        )
    except OidcError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    nclaim = claims.get("nonce")
    if nclaim is None or str(nclaim) != c_nonce:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID token nonce mismatch")
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="ID token missing sub")

    email: str | None = None
    e_raw = claims.get("email")
    if isinstance(e_raw, str) and e_raw:
        email = e_raw
    idp_name: str | None = None
    n_raw = claims.get("name")
    if isinstance(n_raw, str) and n_raw:
        idp_name = n_raw

    for cname in (_C_STATE, _C_VERIFIER, _C_NONCE):
        response.delete_cookie(cname, path="/", secure=secure, httponly=True, samesite="lax")

    try:
        user, roles = await resolve_or_create_oidc_user(
            session,
            entra_sub=sub,
            email=email,
            idp_name=idp_name,
        )
        pair = await issue_tokens(user.tenant_id, user.id, roles)
    except RuntimeError as e:
        if "DEPLOYAI_JWT_PRIVATE_KEY" in str(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Session issuance unavailable (signing key not configured).",
            ) from e
        raise

    response.set_cookie(
        sett.session_access_cookie,
        pair.access_token,
        max_age=sett.access_token_ttl_seconds,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )
    response.set_cookie(
        sett.session_refresh_cookie,
        pair.refresh_jti,
        max_age=sett.refresh_token_ttl_seconds,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )

    return OidcSessionIssued(
        sub=sub,
        user_id=user.id,
        tenant_id=user.tenant_id,
        access_token=pair.access_token,
        refresh_token=pair.refresh_jti,
        token_type=pair.token_type,
        expires_in=pair.expires_in,
        email=email,
        name=idp_name,
    )


@auth_entry_router.get("/login", summary="Start SSO (OIDC when configured)")
async def auth_login() -> Response:
    if not _oidc_fully_configured():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "SSO is not configured. Set OIDC env vars, or use internal test session mint in dev "
                "(docs/auth/sso-setup.md)."
            ),
        )
    return Response(
        status_code=status.HTTP_307_TEMPORARY_REDIRECT,
        headers={"Location": "/auth/oidc/login"},
    )
