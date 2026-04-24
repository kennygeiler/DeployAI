"""SCIM 2.0 /Users (RFC 7643/7644) for Entra ID provisioning (Story 2-3)."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import uuid
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from control_plane.auth.scim_bearer import ScimTenant
from control_plane.auth.session_revoke import revoke_sessions_for_user
from control_plane.db import AppDbSession
from control_plane.domain.app_identity.models import AppUser

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/Users", tags=["scim-users"])

SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"
SCIM_LIST = "urn:ietf:params:scim:api:messages:2.0:ListResponse"
SCIM_ERR = "urn:ietf:params:scim:api:messages:2.0:Error"
MEDIA = "application/scim+json"


def _err(c: int, detail: str) -> dict[str, Any]:
    return {
        "schemas": [SCIM_ERR],
        "status": str(c),
        "detail": detail,
    }


def _audit(
    event: str,
    *,
    tenant_id: uuid.UUID,
    user_id: uuid.UUID,
    scim_id: str | None,
) -> None:
    logger.info(
        "scim.audit",
        extra={
            "event": event,
            "tenant_id": str(tenant_id),
            "subject": str(user_id),
            "scim_id": scim_id,
        },
    )


def _hash_email_pii(value: str | None) -> str | None:
    if not value:
        return None
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _primary_email(emails: Any) -> str | None:
    if not isinstance(emails, list) or not emails:
        return None
    for e in emails:
        if isinstance(e, dict) and e.get("primary") is True:
            v = e.get("value")
            if isinstance(v, str):
                return v
    first = emails[0]
    if isinstance(first, dict):
        v = first.get("value")
        if isinstance(v, str):
            return v
    return None


def _user_resource(u: AppUser) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schemas": [SCIM_USER_SCHEMA],
        "id": str(u.id),
        "userName": u.user_name,
        "active": u.active,
        "meta": {
            "resourceType": "User",
            "version": f'W/"{u.updated_at.timestamp() if u.updated_at else 0}"',
        },
    }
    if u.scim_external_id is not None:
        body["externalId"] = u.scim_external_id
    if u.email:
        body["emails"] = [{"value": u.email, "type": "work", "primary": True}]
    if u.given_name or u.family_name:
        body["name"] = {}
        if u.given_name is not None:
            body["name"]["givenName"] = u.given_name
        if u.family_name is not None:
            body["name"]["familyName"] = u.family_name
    if u.roles is not None:
        body["roles"] = u.roles
    return body


def _scim_list(resources: list[dict[str, Any]], *, total: int, start: int) -> dict[str, Any]:
    return {
        "schemas": [SCIM_LIST],
        "totalResults": total,
        "startIndex": start,
        "itemsPerPage": len(resources),
        "Resources": resources,
    }


_FILTER_EQ = re.compile(
    r'^\s*([a-zA-Z.]+)\s+eq\s+"((?:\\.|[^"\\])*)"\s*$',
    re.IGNORECASE,
)


def _parse_eq_filter(raw: str | None) -> tuple[str, str] | None:
    if not raw or not str(raw).strip():
        return None
    m = _FILTER_EQ.match(str(raw).strip())
    if not m:
        return None
    key = m.group(1).strip().lower()
    return (key, m.group(2))


async def _read_scim_json(request: Request, *, max_bytes: int) -> dict[str, Any]:
    body = await request.body()
    if len(body) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=_err(413, "Payload too large"))
    if not body:
        return {}
    try:
        return cast("dict[str, Any]", json.loads(body.decode("utf-8")))
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_err(400, "Invalid JSON body")) from e


def _normalize_scim_path(path: str | None) -> str:
    """Map RFC 7644 JSON-path style segments (`/name/givenName`) to dotted lower keys."""
    s = (path or "").strip()
    if s.startswith("/"):
        s = s[1:]
    return s.replace("/", ".").lower()


def _apply_op(u: AppUser, op: str, path: str | None, value: Any) -> None:
    p_low = _normalize_scim_path(path)
    o = op.lower()
    if o == "replace":
        if p_low == "username":
            if not isinstance(value, str) or not value.strip():
                raise ValueError("userName value invalid")
            u.user_name = value.strip()
        elif p_low == "active":
            if isinstance(value, bool):
                u.active = value
            elif isinstance(value, str):
                u.active = value.lower() in ("true", "1", "yes")
            else:
                u.active = bool(value)
        elif p_low in ("name.givenname", "name[givenname]"):
            u.given_name = str(value) if value is not None else None
        elif p_low in ("name.familyname", "name[familyname]"):
            u.family_name = str(value) if value is not None else None
        elif p_low == "externalid":
            u.scim_external_id = str(value) if value is not None else None
        elif p_low == "emails" or p_low == "emails[type eq work].value":
            if isinstance(value, list) and value:
                em = _primary_email(value)
                u.email = em
            elif isinstance(value, str):
                u.email = value
        elif p_low == "roles":
            u.roles = value
        elif p_low == "name" and isinstance(value, dict):
            if "givenName" in value:
                u.given_name = str(value["givenName"]) if value.get("givenName") is not None else None
            if "familyName" in value:
                u.family_name = str(value["familyName"]) if value.get("familyName") is not None else None
        else:
            raise ValueError(f"Unsupported replace path: {path}")
    elif o in ("add", "remove") and p_low == "roles":
        if not isinstance(value, (list, dict, str)) and value is not None:
            raise ValueError("roles value invalid")
        u.roles = value
    else:
        raise ValueError(f"Unsupported operation: {op} {path}")


@router.get("", name="scim_list_users", status_code=status.HTTP_200_OK)
async def list_users(
    tenant: ScimTenant,
    session: AppDbSession,
    startindex: int = Query(1, alias="startIndex"),
    count: int = Query(100),
    filter: str | None = Query(
        default=None,
        alias="filter",
        description='SCIM v2: userName eq "..." or emails.value eq "..." (subset).',
    ),
) -> JSONResponse:
    c = 100 if count < 1 or count > 200 else count
    s = 1 if startindex < 1 else startindex
    offset = s - 1

    stmt = select(AppUser).where(AppUser.tenant_id == tenant.id)
    f = _parse_eq_filter(filter)
    if f:
        k, v = f
        if k == "username":
            stmt = stmt.where(func.lower(AppUser.user_name) == v.lower())
        elif k in ("emails.value", "emails"):
            if not v:
                stmt = stmt.where(AppUser.email.is_(None))
            else:
                stmt = stmt.where(func.lower(AppUser.email) == v.lower())
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=_err(400, f"Unsupported $filter attribute: {f[0]}"),
            )

    subq = stmt.subquery()
    total = int((await session.execute(select(func.count()).select_from(subq))).scalar_one())
    r = await session.execute(stmt.order_by(AppUser.user_name).offset(offset).limit(c))
    users = r.scalars().all()
    resources = [_user_resource(x) for x in users]
    return JSONResponse(content=_scim_list(resources, total=total, start=s), media_type=MEDIA)


@router.get("/{user_id}", name="scim_get_user", status_code=status.HTTP_200_OK)
async def get_user(
    user_id: uuid.UUID,
    tenant: ScimTenant,
    session: AppDbSession,
) -> JSONResponse:
    r = await session.execute(select(AppUser).where(AppUser.tenant_id == tenant.id, AppUser.id == user_id))
    u = r.scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_err(404, "User not found"))
    return JSONResponse(content=_user_resource(u), media_type=MEDIA)


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    request: Request,
    tenant: ScimTenant,
    session: AppDbSession,
) -> JSONResponse:
    body = await _read_scim_json(request, max_bytes=1_000_000)
    user_name = body.get("userName")
    if not isinstance(user_name, str) or not user_name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_err(400, "userName is required"))
    ext = body.get("externalId")
    ext_s: str | None
    if ext is None or ext == "":
        ext_s = None
    else:
        ext_s = str(ext)
    emails = body.get("emails")
    email = _primary_email(emails)
    name = body.get("name")
    given = family = None
    if isinstance(name, dict):
        gn, fn = name.get("givenName"), name.get("familyName")
        given = str(gn) if gn is not None else None
        family = str(fn) if fn is not None else None
    active = body.get("active", True)
    if not isinstance(active, bool):
        active = bool(active)
    roles = body.get("roles")
    now = datetime.now(UTC)
    u = AppUser(
        tenant_id=tenant.id,
        scim_external_id=ext_s,
        user_name=user_name.strip(),
        email=email,
        given_name=given,
        family_name=family,
        active=active,
        roles=roles,
        entra_sub=None,
        created_at=now,
        updated_at=now,
    )
    session.add(u)
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_err(409, "User with same userName or externalId already exists"),
        ) from e
    await session.refresh(u)
    scim_n = u.scim_external_id or str(u.id)
    _audit("scim.user.provisioned", tenant_id=tenant.id, user_id=u.id, scim_id=scim_n)
    logger.info(
        "scim.provisioned.email_fingerprint",
        extra={"email_fp": _hash_email_pii(u.email), "tenant_id": str(tenant.id)},
    )
    return JSONResponse(
        status_code=status.HTTP_201_CREATED,
        content=_user_resource(u),
        media_type=MEDIA,
        headers={"Location": f"/scim/v2/Users/{u.id}"},
    )


@router.patch("/{user_id}", status_code=status.HTTP_200_OK)
async def patch_user(
    user_id: uuid.UUID,
    request: Request,
    tenant: ScimTenant,
    session: AppDbSession,
) -> JSONResponse:
    body = await _read_scim_json(request, max_bytes=1_000_000)
    r = await session.execute(select(AppUser).where(AppUser.tenant_id == tenant.id, AppUser.id == user_id))
    u = r.scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_err(404, "User not found"))
    now = datetime.now(UTC)
    if isinstance(body, dict) and "Operations" in body:
        for raw in body.get("Operations") or []:
            if not isinstance(raw, dict):
                continue
            op = str(raw.get("op", "")).strip()
            path = cast("str | None", raw.get("path"))
            val = raw.get("value")
            try:
                _apply_op(u, op, path, val)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_err(400, str(e))) from e
    else:
        for k, v in body.items():
            if k in ("schemas", "id", "meta"):
                continue
            try:
                _apply_op(u, "replace", k, v)
            except ValueError as e:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=_err(400, str(e))) from e
    u.updated_at = now
    try:
        await session.commit()
    except IntegrityError as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_err(409, "Update conflicts with an existing userName or externalId"),
        ) from e
    await session.refresh(u)
    _audit(
        "scim.user.updated",
        tenant_id=tenant.id,
        user_id=u.id,
        scim_id=u.scim_external_id or str(u.id),
    )
    return JSONResponse(content=_user_resource(u), media_type=MEDIA)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: uuid.UUID,
    tenant: ScimTenant,
    session: AppDbSession,
) -> Response:
    r = await session.execute(select(AppUser).where(AppUser.tenant_id == tenant.id, AppUser.id == user_id))
    u = r.scalar_one_or_none()
    if u is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_err(404, "User not found"))
    u.active = False
    u.updated_at = datetime.now(UTC)
    await session.commit()
    await revoke_sessions_for_user(tenant.id, u.id)
    _audit("scim.user.deactivated", tenant_id=tenant.id, user_id=u.id, scim_id=u.scim_external_id or str(u.id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
