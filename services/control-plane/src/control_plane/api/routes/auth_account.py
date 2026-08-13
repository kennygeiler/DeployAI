"""Native email/password auth + self-serve workspaces + invites.

Public surface mounted at ``/api/v1/auth`` (the older session endpoints —
``/auth/refresh``, ``/auth/logout``, ``/auth/oidc/*`` — predate the versioned
prefix and keep their paths; the web BFF is the only caller of either).

Everything session-shaped goes through the SAME
:func:`control_plane.auth.session_service.issue_tokens` path the OIDC
callback and demo mint use — Redis refresh JTI + RS256 access JWT — so the
web middleware, cookie attributes, and ``/auth/refresh`` rotation work
unchanged for password sessions. OIDC (PKCE) remains the enterprise-SSO
option; nothing here touches it.

Anti-enumeration posture on ``/login``:

- Unknown email and wrong password return the identical status + body
  (401 ``invalid email or password``).
- Unknown-email requests still burn one argon2id verify against
  :data:`~control_plane.auth.passwords.DUMMY_HASH` so timing is uniform.
- Failed attempts for a *known* user land a ``user_login_failed`` ledger row;
  unknown identifiers are log-only (ledger rows are tenant-scoped and there
  is no tenant to attribute).

Attempt limiting: dedicated fixed windows (10 attempts / 5 min) keyed per
identifier AND per client IP, independent of the global inbound limiter
(which defaults to off). Redis-backed when ``DEPLOYAI_REDIS_URL`` is set;
otherwise the same single-instance in-memory bucket the global limiter uses
(honest limitation: resets on restart, per-process only).

Invites: single-use tokens, SHA-256 at rest, 7-day expiry. There is NO email
delivery — the create endpoint returns a join path the admin copies and sends
out of band (stated in the UI too).
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Final

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import func, select

from control_plane.api.routes.auth import bearer_access_claims
from control_plane.auth.passwords import (
    DUMMY_HASH,
    hash_password,
    needs_rehash,
    password_policy_error,
    verify_password,
)
from control_plane.auth.session_service import SessionPair, issue_tokens, revoke_all_for_user
from control_plane.config.settings import get_settings
from control_plane.db import AppDbSession
from control_plane.domain.app_identity.models import AppTenant, AppUser, UserInvite
from control_plane.exceptions import AccountProvisionError
from control_plane.infra.rate_limit import (
    MemoryTokenBucketLimiter,
    redis_fixed_window_check,
)
from control_plane.infra.redis_client import get_async_redis
from control_plane.ledger import emit_ledger_event
from control_plane.services.account_provision import provision_platform_account
from control_plane.services.oidc_user import roles_for_access_token

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/auth", tags=["auth-account"])

# Tenant-grantable roles an admin may put on an invite. platform_admin (cross-
# tenant operator), demo_guest (mint-only), and pending_assignment (SSO limbo)
# are deliberately not invitable.
INVITABLE_ROLES: Final[frozenset[str]] = frozenset(
    {
        "customer_admin",
        "deployment_strategist",
        "fde",
        "biz_dev",
        "successor_strategist",
        "customer_records_officer",
        "external_auditor",
    }
)

ADMIN_ROLES: Final[frozenset[str]] = frozenset({"customer_admin", "platform_admin"})

INVITE_TTL = timedelta(days=7)

# Dedicated auth attempt limiter: small fixed window, generic 429. Independent
# of the global inbound limiter on purpose (that one defaults to off).
_ATTEMPT_BUDGET: Final = 10
_ATTEMPT_WINDOW_SECONDS: Final = 300
_ATTEMPT_KEY_PREFIX: Final = "auth-attempt:"

_memory_attempts = MemoryTokenBucketLimiter()

_GENERIC_LOGIN_FAIL: Final = "invalid email or password"
_GENERIC_429: Final = "too many attempts; try again later"


def reset_auth_attempt_limiter() -> None:
    """Test hook (in-memory backend only; Redis state lives in Redis)."""
    _memory_attempts.reset()


def _client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for")
    if xff:
        first = xff.split(",")[0].strip()
        if first:
            return first
    return request.client.host if request.client else "unknown"


async def _attempt_limited(scope: str, identifier: str) -> bool:
    """One fixed-window check; ``True`` means over budget (caller 429s)."""
    digest = hashlib.sha256(identifier.encode()).hexdigest()[:32]
    key = f"{_ATTEMPT_KEY_PREFIX}{scope}:{digest}"
    if os.environ.get("DEPLOYAI_REDIS_URL"):
        try:
            decision = await redis_fixed_window_check(
                get_async_redis(),
                key,
                budget=_ATTEMPT_BUDGET,
                window_seconds=_ATTEMPT_WINDOW_SECONDS,
            )
            return not decision.allowed
        except Exception:
            # Same posture as the inbound limiter: Redis loss fails open for
            # availability; argon2 cost still brakes brute force.
            logger.warning("auth_attempt_limit.redis_unavailable — failing open", exc_info=True)
            return False
    decision = _memory_attempts.check(
        key,
        capacity=float(_ATTEMPT_BUDGET),
        refill_per_second=_ATTEMPT_BUDGET / _ATTEMPT_WINDOW_SECONDS,
        now=time.monotonic(),
    )
    return not decision.allowed


async def _require_attempts(request: Request, scope: str, identifier: str | None) -> None:
    """429 (generic body) when either the per-IP or per-identifier window is spent."""
    if await _attempt_limited(scope, f"ip:{_client_ip(request)}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_GENERIC_429)
    if identifier and await _attempt_limited(scope, f"id:{identifier}"):
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=_GENERIC_429)


def _request_is_https(request: Request) -> bool:
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    return proto == "https"


def _set_session_cookies(response: Response, pair: SessionPair, *, secure: bool) -> None:
    """Same names + attributes the OIDC callback sets (dep_access / dep_refresh)."""
    s = get_settings()
    response.set_cookie(
        s.session_access_cookie,
        pair.access_token,
        max_age=s.access_token_ttl_seconds,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )
    response.set_cookie(
        s.session_refresh_cookie,
        pair.refresh_jti,
        max_age=s.refresh_token_ttl_seconds,
        httponly=True,
        samesite="lax",
        path="/",
        secure=secure,
    )


class AccountSessionIssued(BaseModel):
    """Same shape ``parseCpSessionIssued`` on the web expects from the OIDC
    callback (access_token / refresh_token / tenant_id / expires_in)."""

    user_id: uuid.UUID
    tenant_id: uuid.UUID
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int
    email: str | None = None
    name: str | None = None
    roles: list[str] = Field(default_factory=list)


def _session_response(user: AppUser, roles: list[str], pair: SessionPair) -> AccountSessionIssued:
    return AccountSessionIssued(
        user_id=user.id,
        tenant_id=user.tenant_id,
        access_token=pair.access_token,
        refresh_token=pair.refresh_jti,
        expires_in=pair.expires_in,
        email=user.email,
        name=user.given_name,
        roles=roles,
    )


def _signing_unavailable(e: RuntimeError) -> HTTPException | None:
    if "DEPLOYAI_JWT_PRIVATE_KEY" in str(e):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Session issuance unavailable (signing key not configured).",
        )
    return None


async def _find_credentialed_user(session: AppDbSession, email_norm: str) -> AppUser | None:
    r = await session.execute(
        select(AppUser)
        .where(
            func.lower(AppUser.email) == email_norm,
            AppUser.password_hash.is_not(None),
            AppUser.active.is_(True),
        )
        .order_by(AppUser.created_at.asc())
        .limit(1)
    )
    return r.scalar_one_or_none()


async def _emit_auth_ledger(
    session: AppDbSession,
    *,
    tenant_id: uuid.UUID,
    actor_id: str | None,
    source_kind: str,
    summary: str,
    detail: dict[str, object],
    affects_user_id: uuid.UUID | None = None,
) -> None:
    """One tenant-scoped audit row; caller's route owns the commit."""
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=None,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=actor_id,
        source_kind=source_kind,
        source_ref=None,
        summary=summary,
        detail=dict(detail),
        affects=(("app_user", affects_user_id),) if affects_user_id is not None else (),
    )


# ---------------------------------------------------------------------------
# Signup
# ---------------------------------------------------------------------------


class SignupBody(BaseModel):
    email: EmailStr
    password: str
    workspace_name: str = Field(..., min_length=1, max_length=512)
    display_name: str = Field(..., min_length=1, max_length=200)


@router.post("/signup", response_model=AccountSessionIssued, status_code=status.HTTP_201_CREATED)
async def signup(
    body: SignupBody,
    request: Request,
    response: Response,
    session: AppDbSession,
) -> AccountSessionIssued:
    """Self-serve workspace creation (env-gated: ``DEPLOYAI_SELF_SERVE_SIGNUP``).

    Provisions through the same canonical path as ``POST /platform/accounts``
    (tenant + DEK wrap + empty-baseline check + initial user) with the creator
    as ``customer_admin`` holding an argon2id credential, then issues a session
    exactly like the OIDC callback (cookies included). 404 when disabled so a
    probe cannot distinguish "off" from "absent" (mirrors the demo mint).

    Duplicate email returns 409 — mild enumeration on a route that only exists
    on deploys that opted into public workspace creation; accepted trade-off
    versus silently orphaning the signup.
    """
    if not get_settings().self_serve_signup_enabled:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Self-serve signup is disabled (set DEPLOYAI_SELF_SERVE_SIGNUP=1).",
        )
    await _require_attempts(request, "signup", None)
    policy_err = password_policy_error(body.password)
    if policy_err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=policy_err)
    email_norm = str(body.email).strip().lower()
    if await _find_credentialed_user(session, email_norm) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Sign in instead.",
        )
    try:
        created = await provision_platform_account(
            session,
            organization_name=body.workspace_name,
            initial_strategist_email=email_norm,
            actor_sub=None,
            initial_roles=["customer_admin"],
            password_hash=hash_password(body.password),
            display_name=body.display_name.strip(),
        )
    except AccountProvisionError:
        logger.exception("auth.signup.provision_failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Workspace could not be created",
        ) from None
    user = await session.get(AppUser, created.initial_strategist_user_id)
    if user is None:  # pragma: no cover — row committed one statement ago
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="provision inconsistent")
    roles = roles_for_access_token(user.roles)
    try:
        pair = await issue_tokens(user.tenant_id, user.id, roles)
    except RuntimeError as e:
        http = _signing_unavailable(e)
        if http:
            raise http from e
        raise
    await _emit_auth_ledger(
        session,
        tenant_id=user.tenant_id,
        actor_id=str(user.id),
        source_kind="account_signup",
        summary=f"Workspace '{body.workspace_name.strip()}' created via self-serve signup",
        detail={"workspace_name": body.workspace_name.strip(), "roles": roles},
        affects_user_id=user.id,
    )
    await session.commit()
    _set_session_cookies(response, pair, secure=_request_is_https(request))
    return _session_response(user, roles, pair)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------


class LoginBody(BaseModel):
    email: EmailStr
    password: str


@router.post("/login", response_model=AccountSessionIssued)
async def login(
    body: LoginBody,
    request: Request,
    response: Response,
    session: AppDbSession,
) -> AccountSessionIssued:
    """Email/password login. Uniform 401 + dummy-verify for unknown identifiers
    (see module docstring); rehash-on-verify keeps old hashes current."""
    email_norm = str(body.email).strip().lower()
    await _require_attempts(request, "login", email_norm)
    user = await _find_credentialed_user(session, email_norm)
    if user is None or user.password_hash is None:
        verify_password(DUMMY_HASH, body.password)
        logger.info("auth.login.failed_unknown_identifier")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_FAIL)
    if not verify_password(user.password_hash, body.password):
        await _emit_auth_ledger(
            session,
            tenant_id=user.tenant_id,
            actor_id=str(user.id),
            source_kind="user_login_failed",
            summary="Password login failed (wrong password)",
            detail={},
            affects_user_id=user.id,
        )
        await session.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_GENERIC_LOGIN_FAIL)
    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(body.password)
        user.password_updated_at = datetime.now(UTC)
    roles = roles_for_access_token(user.roles)
    try:
        pair = await issue_tokens(user.tenant_id, user.id, roles)
    except RuntimeError as e:
        http = _signing_unavailable(e)
        if http:
            raise http from e
        raise
    await _emit_auth_ledger(
        session,
        tenant_id=user.tenant_id,
        actor_id=str(user.id),
        source_kind="user_login_succeeded",
        summary="Password login succeeded",
        detail={},
        affects_user_id=user.id,
    )
    await session.commit()
    _set_session_cookies(response, pair, secure=_request_is_https(request))
    return _session_response(user, roles, pair)


# ---------------------------------------------------------------------------
# Authed helpers (me / password change)
# ---------------------------------------------------------------------------


def _claims_ids(claims: dict[str, object]) -> tuple[uuid.UUID, uuid.UUID]:
    sub, tid = claims.get("sub"), claims.get("tid")
    try:
        return uuid.UUID(str(tid)), uuid.UUID(str(sub))
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject") from None


class MeResponse(BaseModel):
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    tenant_name: str | None
    email: str | None
    display_name: str | None
    roles: list[str]
    has_password: bool
    """False for SSO/SCIM-only users — the account page hides the change-password form."""


@router.get("/me", response_model=MeResponse)
async def me(
    session: AppDbSession,
    claims: Annotated[dict[str, object], Depends(bearer_access_claims)],
) -> MeResponse:
    """Profile for the session's user (the account page's data source)."""
    tenant_id, user_id = _claims_ids(claims)
    user = await session.get(AppUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    tenant = await session.get(AppTenant, tenant_id)
    raw_roles = claims.get("roles")
    roles = [str(r) for r in raw_roles] if isinstance(raw_roles, list) else []
    return MeResponse(
        user_id=user.id,
        tenant_id=user.tenant_id,
        tenant_name=tenant.name if tenant else None,
        email=user.email,
        display_name=user.given_name,
        roles=roles,
        has_password=user.password_hash is not None,
    )


class PasswordChangeBody(BaseModel):
    current_password: str
    new_password: str


@router.post("/password", status_code=status.HTTP_200_OK)
async def change_password(
    body: PasswordChangeBody,
    request: Request,
    response: Response,
    session: AppDbSession,
    claims: Annotated[dict[str, object], Depends(bearer_access_claims)],
) -> AccountSessionIssued:
    """Verify current password, store a fresh argon2id hash, revoke every
    refresh session for the user (the session service's per-user JTI index
    supports full enumeration — there is no "all except this one", so ALL are
    revoked and a brand-new pair is minted + returned for the caller to keep).
    Outstanding *access* JWTs are stateless and stay valid until expiry
    (<= 15 min default); refresh is what actually dies here."""
    tenant_id, user_id = _claims_ids(claims)
    await _require_attempts(request, "pwchange", str(user_id))
    user = await session.get(AppUser, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="user not found")
    if user.password_hash is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This account signs in with SSO and has no password to change.",
        )
    if not verify_password(user.password_hash, body.current_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="current password is incorrect")
    policy_err = password_policy_error(body.new_password)
    if policy_err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=policy_err)
    user.password_hash = hash_password(body.new_password)
    user.password_updated_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    await revoke_all_for_user(tenant_id, user_id)
    roles = roles_for_access_token(user.roles)
    pair = await issue_tokens(tenant_id, user_id, roles)
    await _emit_auth_ledger(
        session,
        tenant_id=tenant_id,
        actor_id=str(user_id),
        source_kind="password_changed",
        summary="Account password changed; other sessions revoked",
        detail={},
        affects_user_id=user_id,
    )
    await session.commit()
    _set_session_cookies(response, pair, secure=_request_is_https(request))
    return _session_response(user, roles, pair)


# ---------------------------------------------------------------------------
# Invites
# ---------------------------------------------------------------------------


def _require_admin(claims: dict[str, object]) -> None:
    roles = claims.get("roles")
    role_list = [str(r) for r in roles] if isinstance(roles, list) else []
    if not ADMIN_ROLES.intersection(role_list):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="customer_admin role required",
        )


def _hash_invite_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class InviteCreateBody(BaseModel):
    email: EmailStr
    role: str


class InviteCreated(BaseModel):
    invite_id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    join_path: str
    """Relative path (``/join/<token>``) — the web BFF prefixes its own origin.
    This response is the ONLY place the raw token ever appears; copy it now."""


class InvitePending(BaseModel):
    invite_id: uuid.UUID
    email: str
    role: str
    expires_at: datetime
    created_at: datetime


@router.post("/invites", response_model=InviteCreated, status_code=status.HTTP_201_CREATED)
async def create_invite(
    body: InviteCreateBody,
    session: AppDbSession,
    claims: Annotated[dict[str, object], Depends(bearer_access_claims)],
) -> InviteCreated:
    """Admin-only. Returns a join path containing the single-use token; the
    token is stored hashed and cannot be recovered later. No email is sent —
    there is no mail infrastructure; the admin copies the link."""
    _require_admin(claims)
    tenant_id, actor_user_id = _claims_ids(claims)
    if body.role not in INVITABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"role must be one of: {', '.join(sorted(INVITABLE_ROLES))}",
        )
    email_norm = str(body.email).strip().lower()
    token = secrets.token_urlsafe(32)
    invite = UserInvite(
        tenant_id=tenant_id,
        email=email_norm,
        role=body.role,
        token_hash=_hash_invite_token(token),
        invited_by_user_id=actor_user_id,
        expires_at=datetime.now(UTC) + INVITE_TTL,
    )
    session.add(invite)
    await session.flush()
    await _emit_auth_ledger(
        session,
        tenant_id=tenant_id,
        actor_id=str(actor_user_id),
        source_kind="invite_created",
        summary=f"Invite created for {email_norm} as {body.role}",
        detail={"invited_email": email_norm, "role": body.role, "invite_id": str(invite.id)},
    )
    await session.commit()
    return InviteCreated(
        invite_id=invite.id,
        email=email_norm,
        role=body.role,
        expires_at=invite.expires_at,
        join_path=f"/join/{token}",
    )


@router.get("/invites", response_model=list[InvitePending])
async def list_pending_invites(
    session: AppDbSession,
    claims: Annotated[dict[str, object], Depends(bearer_access_claims)],
) -> list[InvitePending]:
    """Admin-only: unaccepted, unexpired invites for the caller's tenant."""
    _require_admin(claims)
    tenant_id, _ = _claims_ids(claims)
    r = await session.execute(
        select(UserInvite)
        .where(
            UserInvite.tenant_id == tenant_id,
            UserInvite.accepted_at.is_(None),
            UserInvite.expires_at > datetime.now(UTC),
        )
        .order_by(UserInvite.created_at.desc())
    )
    return [
        InvitePending(
            invite_id=i.id,
            email=i.email,
            role=i.role,
            expires_at=i.expires_at,
            created_at=i.created_at,
        )
        for i in r.scalars().all()
    ]


async def _resolve_live_invite(session: AppDbSession, token: str) -> UserInvite:
    """404 (one generic detail) for unknown, expired, and already-used tokens."""
    r = await session.execute(select(UserInvite).where(UserInvite.token_hash == _hash_invite_token(token)))
    invite = r.scalar_one_or_none()
    if invite is None or invite.accepted_at is not None or invite.expires_at <= datetime.now(UTC):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="This invite link is invalid, expired, or already used.",
        )
    return invite


class InvitePreview(BaseModel):
    email: str
    role: str
    workspace_name: str | None
    expires_at: datetime


@router.get("/invites/preview", response_model=InvitePreview)
async def preview_invite(
    session: AppDbSession,
    request: Request,
    token: Annotated[str, Query(min_length=1)],
) -> InvitePreview:
    """Public: what the /join page shows before the invitee sets a password."""
    await _require_attempts(request, "invite", None)
    invite = await _resolve_live_invite(session, token)
    tenant = await session.get(AppTenant, invite.tenant_id)
    return InvitePreview(
        email=invite.email,
        role=invite.role,
        workspace_name=tenant.name if tenant else None,
        expires_at=invite.expires_at,
    )


class InviteAcceptBody(BaseModel):
    token: str = Field(..., min_length=1)
    password: str
    display_name: str = Field(..., min_length=1, max_length=200)


@router.post("/invites/accept", response_model=AccountSessionIssued, status_code=status.HTTP_201_CREATED)
async def accept_invite(
    body: InviteAcceptBody,
    request: Request,
    response: Response,
    session: AppDbSession,
) -> AccountSessionIssued:
    """Public: redeem a live invite — creates the user in the invite's tenant
    with the invite's role + an argon2id credential, marks the invite used,
    and issues a session (cookies included) so the invitee lands signed in."""
    await _require_attempts(request, "invite", None)
    invite = await _resolve_live_invite(session, body.token)
    policy_err = password_policy_error(body.password)
    if policy_err:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=policy_err)
    if await _find_credentialed_user(session, invite.email) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An account with this email already exists. Sign in instead.",
        )
    now = datetime.now(UTC)
    user = AppUser(
        tenant_id=invite.tenant_id,
        scim_external_id=None,
        user_name=invite.email,
        email=invite.email,
        given_name=body.display_name.strip(),
        active=True,
        roles=[invite.role],
        password_hash=hash_password(body.password),
        password_updated_at=now,
    )
    session.add(user)
    await session.flush()
    invite.accepted_at = now
    invite.accepted_user_id = user.id
    roles = roles_for_access_token(user.roles)
    try:
        pair = await issue_tokens(user.tenant_id, user.id, roles)
    except RuntimeError as e:
        http = _signing_unavailable(e)
        if http:
            raise http from e
        raise
    await _emit_auth_ledger(
        session,
        tenant_id=invite.tenant_id,
        actor_id=str(user.id),
        source_kind="invite_accepted",
        summary=f"Invite accepted by {invite.email} as {invite.role}",
        detail={"invite_id": str(invite.id), "role": invite.role},
        affects_user_id=user.id,
    )
    await session.commit()
    _set_session_cookies(response, pair, secure=_request_is_https(request))
    return _session_response(user, roles, pair)
