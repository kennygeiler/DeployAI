"""M365 calendar → canonical memory (Epic 3 Story 3-1)."""

from __future__ import annotations

import logging
import time
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.auth.oidc_flow import fetch_openid_metadata
from control_plane.config.settings import ControlPlaneSettings, get_settings
from control_plane.db import tenant_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.integrations.models import Integration
from control_plane.integrations.m365_oauth import refresh_delegation_access

_LOG = logging.getLogger(__name__)
_GRAPH = "https://graph.microsoft.com/v1.0"


def _cfg_dict(x: object) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _event_occurred_at(ev: dict[str, Any]) -> datetime:
    s = ev.get("start")
    if isinstance(s, dict):
        raw = s.get("dateTime")
        if isinstance(raw, str) and raw:
            if raw.endswith("Z"):
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            return datetime.fromisoformat(raw)
    return datetime.now(UTC)


def _event_payload_subset(ev: dict[str, Any]) -> dict[str, Any]:
    keys = ("id", "subject", "start", "end", "organizer", "isCancelled", "type", "webLink", "iCalUId")
    return {k: ev[k] for k in keys if k in ev}


async def _source_ref_exists(t_session: AsyncSession, *, tenant_id: uuid.UUID, source_ref: str) -> bool:
    r = await t_session.execute(
        select(CanonicalMemoryEvent.id).where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            CanonicalMemoryEvent.source_ref == source_ref,
        )
    )
    return r.scalar_one_or_none() is not None


async def _ensure_access_token(
    httpx_client: httpx.AsyncClient,
    meta: dict[str, Any],
    it: Integration,
    creds: ControlPlaneSettings,
) -> str:
    token_endpoint = str(meta["token_endpoint"])
    c = _cfg_dict(it.config or {})
    oauth = _cfg_dict(c.get("oauth") or {})
    at = oauth.get("access_token")
    if not isinstance(at, str):
        at = None
    exp = float(oauth.get("expires_at_epoch") or 0)
    rt = oauth.get("refresh_token")
    if not isinstance(rt, str):
        rt = None
    if at and time.time() < exp - 60:
        return at
    if not rt:
        raise ValueError("integration missing refresh_token; reconnect OAuth")
    rclient = creds.m365_oauth_client_id or creds.oidc_client_id
    rsec = creds.m365_oauth_client_secret or creds.oidc_client_secret
    if not rclient or not rsec:
        raise ValueError("M365 client credentials are not configured")
    new_toks = await refresh_delegation_access(
        httpx_client,
        token_endpoint,
        refresh_token=rt,
        client_id=rclient,
        client_secret=rsec,
    )
    at2 = str(new_toks["access_token"])
    new_rt = new_toks.get("refresh_token", rt)
    if not isinstance(new_rt, str):
        new_rt = rt
    ex_in = int(new_toks.get("expires_in") or 3600)
    it.config = {
        **c,
        "oauth": {
            **oauth,
            "access_token": at2,
            "refresh_token": new_rt,
            "expires_at_epoch": time.time() + ex_in,
        },
    }
    return at2


async def run_calendar_delta_sync(
    app_session: AsyncSession,
    it: Integration,
) -> dict[str, Any]:
    """Use Graph ``calendarView/delta``; insert idempotent ``calendar.event`` nodes; store ``graph.delta_link``."""
    s = get_settings()
    m_creds = s.m365_oauth_client_id or s.oidc_client_id
    m_sec = s.m365_oauth_client_secret or s.oidc_client_secret
    if not m_creds or not m_sec:
        raise ValueError("M365 OAuth is not configured")
    if it.provider != "m365_calendar":
        raise ValueError("integration is not m365_calendar")
    tid = it.tenant_id
    c0 = _cfg_dict(it.config or {})
    graph_cfg0 = _cfg_dict(c0.get("graph") or {})
    dr = graph_cfg0.get("delta_link")
    delta_stored: str | None = dr if isinstance(dr, str) else None
    o0 = _cfg_dict(c0.get("oauth") or {})
    if not o0.get("refresh_token"):
        raise ValueError("integration has no OAuth tokens; run /connect first")
    issuer = (s.m365_oauth_issuer or s.oidc_issuer or "").strip()
    if not issuer:
        raise ValueError("issuer not configured")

    inserted = 0
    new_delta: str | None = None
    next_url: str | None
    if delta_stored:
        next_url = delta_stored
    else:
        now = datetime.now(UTC)
        start = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = (now + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
        next_url = f"{_GRAPH}/me/calendarView/delta?startDateTime={start}&endDateTime={end}"

    async with httpx.AsyncClient(timeout=30.0) as gclient:
        meta = await fetch_openid_metadata(gclient, issuer)
        atok = await _ensure_access_token(gclient, meta, it, s)
        await app_session.flush()
        while next_url:
            r = await gclient.get(
                str(next_url),
                headers={"Authorization": f"Bearer {atok}", "Prefer": "odata.maxpagesize=100"},
            )
            if r.status_code == 401:
                atok = await _ensure_access_token(gclient, meta, it, s)
                await app_session.flush()
                r = await gclient.get(
                    str(next_url),
                    headers={"Authorization": f"Bearer {atok}", "Prefer": "odata.maxpagesize=100"},
                )
            if r.is_error:
                _LOG.warning("graph request failed: %s %s", r.status_code, r.text[:300])
                raise ValueError(f"Graph error: {r.status_code}")
            page: dict[str, Any] = r.json()
            for ev in page.get("value") or []:
                if not isinstance(ev, dict):
                    continue
                if "@removed" in ev:
                    continue
                eid = ev.get("id")
                if not isinstance(eid, str) or not eid:
                    continue
                source_ref = f"graph:calendar_event:{eid}"
                pld = _event_payload_subset(ev)
                occ = _event_occurred_at(ev)
                async with tenant_session(tid) as t_sess:
                    if await _source_ref_exists(t_sess, tenant_id=tid, source_ref=source_ref):
                        continue
                    t_sess.add(
                        CanonicalMemoryEvent(
                            tenant_id=tid,
                            event_type="calendar.event",
                            occurred_at=occ,
                            source_ref=source_ref,
                            payload=pld,
                        )
                    )
                    await t_sess.commit()
                inserted += 1
            dlink = page.get("@odata.deltaLink")
            if isinstance(dlink, str) and dlink:
                new_delta = dlink
            nxt = page.get("@odata.nextLink")
            next_url = nxt if isinstance(nxt, str) else None

    conf = _cfg_dict(it.config or {})
    g2 = {
        **_cfg_dict(conf.get("graph") or {}),
        "delta_link": new_delta or graph_cfg0.get("delta_link"),
    }
    it.config = {
        **conf,
        "graph": g2,
        "graph_meta": {
            **_cfg_dict(conf.get("graph_meta") or {}),
            "last_sync_at": time.time(),
        },
    }
    await app_session.flush()
    return {"inserted": inserted, "delta_link": new_delta}
