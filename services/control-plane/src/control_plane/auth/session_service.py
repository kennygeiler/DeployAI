"""Issue/refresh refresh tokens in Redis; RS256 access JWTs (Story 2-4)."""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

from control_plane.auth.jwt_tokens import create_access_token
from control_plane.auth.session_keys import jti_global_lookup_key, session_refresh_key, user_refresh_index_key
from control_plane.config.settings import get_settings
from control_plane.infra.redis_client import get_async_redis

logger = logging.getLogger(__name__)


class InvalidRefreshError(Exception):
    """Refresh JTI missing, expired, or payload invalid."""


class TenantMismatchError(Exception):
    """Refresh payload tenant does not match request."""


@dataclass(frozen=True)
class SessionPair:
    access_token: str
    refresh_jti: str
    token_type: str = "Bearer"
    expires_in: int = 0


def _jti_str(j: str | bytes) -> str:
    if isinstance(j, bytes):
        return j.decode("utf-8")
    return j


def _parse_session_blob(
    raw: str,
) -> tuple[uuid.UUID, uuid.UUID, list[str]]:
    """Load refresh JSON; raise InvalidRefreshError on bad data (never KeyError/JSONError)."""
    try:
        obj: Any = json.loads(raw)
    except json.JSONDecodeError as e:
        raise InvalidRefreshError("corrupt session record") from e
    if not isinstance(obj, dict):
        raise InvalidRefreshError("invalid session record shape")
    try:
        tenant_id = uuid.UUID(str(obj["tenant_id"]))
        user_id = uuid.UUID(str(obj["user_id"]))
    except (KeyError, ValueError) as e:
        raise InvalidRefreshError("invalid session record fields") from e
    rraw = obj.get("roles", [])
    if isinstance(rraw, list) and all(isinstance(x, str) for x in rraw):
        roles: list[str] = list(rraw)
    else:
        roles = []
    return tenant_id, user_id, roles


async def _touch_user_index(
    r: redis.Redis,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    refresh_jti: str,
    ex: int,
) -> None:
    idx = user_refresh_index_key(tenant_id, user_id)
    await r.sadd(idx, refresh_jti)  # type: ignore[misc]
    await r.expire(idx, ex)


async def _remove_refresh_record(
    r: redis.Redis,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    refresh_jti: str,
) -> None:
    sk = session_refresh_key(tenant_id, refresh_jti)
    jk = jti_global_lookup_key(refresh_jti)
    await r.delete(sk)
    await r.delete(jk)
    idx = user_refresh_index_key(tenant_id, user_id)
    await r.srem(idx, refresh_jti)  # type: ignore[misc]


async def issue_tokens(
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    roles: list[str],
) -> SessionPair:
    """Mint opaque refresh (UUID) in Redis + RS256 access token."""
    s = get_settings()
    r = get_async_redis()
    refresh_jti = str(uuid.uuid4())
    access_jti = str(uuid.uuid4())
    s_ex = s.refresh_token_ttl_seconds
    payload: dict[str, Any] = {
        "user_id": str(user_id),
        "tenant_id": str(tenant_id),
        "roles": roles,
    }
    key = session_refresh_key(tenant_id, refresh_jti)
    jti_lookup = jti_global_lookup_key(refresh_jti)
    blob = json.dumps(payload)
    await r.setex(key, s_ex, blob)
    await r.setex(jti_lookup, s_ex, blob)
    await _touch_user_index(r, tenant_id, user_id, refresh_jti, s_ex)
    access = create_access_token(
        sub=str(user_id),
        tid=str(tenant_id),
        roles=roles,
        access_jti=access_jti,
    )
    return SessionPair(
        access_token=access,
        refresh_jti=refresh_jti,
        expires_in=s.access_token_ttl_seconds,
    )


async def refresh_tokens(tenant_id: uuid.UUID, refresh_jti: str) -> SessionPair:
    """Validate refresh, rotate (delete old, mint new) with the same role list."""
    r = get_async_redis()
    raw = await r.get(jti_global_lookup_key(refresh_jti))
    if not raw:
        raise InvalidRefreshError("expired or unknown refresh")
    stored_tid, user_id, roles = _parse_session_blob(raw)
    if stored_tid != tenant_id:
        raise TenantMismatchError
    await _remove_refresh_record(r, stored_tid, user_id, refresh_jti)
    if not roles:
        raise InvalidRefreshError("session missing roles; re-authenticate")
    return await issue_tokens(stored_tid, user_id, roles)


async def logout(tenant_id: uuid.UUID, refresh_jti: str) -> bool:
    """Remove refresh keys. Return False if unknown. Raise TenantMismatchError if JTI is for another tenant."""
    r = get_async_redis()
    raw = await r.get(jti_global_lookup_key(refresh_jti))
    if not raw:
        return False
    stored_tid, user_id, _roles = _parse_session_blob(raw)
    if stored_tid != tenant_id:
        raise TenantMismatchError
    await _remove_refresh_record(r, stored_tid, user_id, refresh_jti)
    return True


async def revoke_all_for_user(tenant_id: uuid.UUID, user_id: uuid.UUID) -> int:
    """Delete all refresh session keys and the user index. Returns number of session keys removed."""
    r = get_async_redis()
    idx = user_refresh_index_key(tenant_id, user_id)
    jtis = await r.smembers(idx)  # type: ignore[misc]
    if not jtis:
        return 0
    async with r.pipeline(transaction=True) as pipe:
        for jti in jtis:
            j = _jti_str(jti)
            pipe.delete(session_refresh_key(tenant_id, j))
            pipe.delete(jti_global_lookup_key(j))
        pipe.delete(idx)
        await pipe.execute()
    n = len(jtis)
    logger.info(
        "sessions.revoke_all",
        extra={"tenant_id": str(tenant_id), "user_id": str(user_id), "deleted_refresh_keys": n},
    )
    return n
