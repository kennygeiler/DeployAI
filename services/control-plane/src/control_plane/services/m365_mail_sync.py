"""M365 / Exchange thread → canonical memory (Epic 3 Story 3-2, FR10, FR16)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.settings import ControlPlaneSettings, get_settings
from control_plane.db import tenant_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.integrations.models import Integration
from control_plane.infra.email_body_store import store_email_body
from control_plane.integrations.m365_oauth import GRAPH_MAIL_SCOPES, fetch_metadata, refresh_delegation_access

_LOG = logging.getLogger(__name__)
_GRAPH = "https://graph.microsoft.com/v1.0"
_MAIL_SELECT = (
    "id,conversationId,subject,from,toRecipients,ccRecipients,sentDateTime,body,hasAttachments,internetMessageId"
)
_UTC = ZoneInfo("UTC")


def _cfg_dict(x: object) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _body_text(body: object) -> str:
    if not isinstance(body, dict):
        return ""
    c = body.get("content")
    if isinstance(c, str):
        return c
    return ""


def _addr_from_recipient(r: object) -> str | None:
    if not isinstance(r, dict):
        return None
    ea = r.get("emailAddress")
    if not isinstance(ea, dict):
        return None
    a = ea.get("address")
    if isinstance(a, str) and a:
        return a
    n = ea.get("name")
    if isinstance(n, str) and n:
        return n
    return None


def _collect_participants(msgs: list[dict[str, Any]]) -> list[str]:
    s: set[str] = set()
    for m in msgs:
        for r in m.get("toRecipients") or []:
            a = _addr_from_recipient(r)
            if a:
                s.add(a)
        for r in m.get("ccRecipients") or []:
            a = _addr_from_recipient(r)
            if a:
                s.add(a)
        a = _addr_from_recipient(m.get("from"))
        if a:
            s.add(a)
    return sorted(s)


def _fingerprint_for_thread(message_ids: list[str]) -> str:
    return hashlib.sha256(",".join(sorted(message_ids)).encode("utf-8")).hexdigest()[:20]


def _filter_conversation_odata(conversation_id: str) -> str:
    s = str(conversation_id).replace("'", "''")
    return f"conversationId eq '{s}'"


def _source_ref_for_thread(conversation_id: str, message_ids: list[str]) -> str:
    return f"graph:email_thread:{conversation_id}@{_fingerprint_for_thread(message_ids)}"


async def _source_ref_exists(t_session: AsyncSession, *, tenant_id: uuid.UUID, source_ref: str) -> bool:
    r = await t_session.execute(
        select(CanonicalMemoryEvent.id).where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            CanonicalMemoryEvent.source_ref == source_ref,
        )
    )
    return r.scalar_one_or_none() is not None


async def _list_thread_messages_paged(
    gclient: httpx.AsyncClient,
    *,
    auth: str,
    conv: str,
) -> list[dict[str, Any]]:
    """All messages in a conversation (Graph pages at 100)."""
    base = f"{_GRAPH}/me/messages"
    q: dict[str, str] = {
        "$select": _MAIL_SELECT,
        "$orderby": "sentDateTime",
        "$top": "100",
        "$filter": _filter_conversation_odata(conv),
    }
    out: list[dict[str, Any]] = []
    url: str = base
    use_params: dict[str, str] | None = q
    while True:
        r = await _graph_get(gclient, url, auth=auth, params=use_params)
        if r.is_error:
            _LOG.warning("thread messages page failed: %s", r.status_code)
            return out
        tj: dict[str, Any] = r.json()
        for x in tj.get("value") or []:
            if isinstance(x, dict):
                out.append(x)
        nxt = tj.get("@odata.nextLink")
        if not isinstance(nxt, str) or not nxt:
            break
        url = nxt
        use_params = None
    return out


async def _graph_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    auth: str,
    params: Mapping[str, str] | None = None,
) -> httpx.Response:
    h = {"Authorization": f"Bearer {auth}", "Prefer": "odata.maxpagesize=100"}
    r = await client.get(str(url), headers=h, params=params, timeout=60.0)
    if r.status_code == 429:
        ra = r.headers.get("Retry-After")
        wait = 2
        if ra is not None:
            try:
                wait = int(float(ra))
            except ValueError:
                wait = 2
        wait = min(max(wait, 1), 60)
        await asyncio.sleep(float(wait))
        r = await client.get(str(url), headers=h, params=params, timeout=60.0)
    return r


def _parse_graph_dt(s: str) -> datetime:
    s2 = s.strip()
    if s2.endswith("Z"):
        return datetime.fromisoformat(s2.replace("Z", "+00:00"))
    if len(s2) > 10 and s2[-6] in "+-":
        return datetime.fromisoformat(s2)
    return datetime.fromisoformat(s2 + "+00:00").astimezone(_UTC)


def _message_sort_key(m: dict[str, Any]) -> str:
    return str(m.get("sentDateTime") or m.get("receivedDateTime") or "")


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
        scope=GRAPH_MAIL_SCOPES,
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


INBOX_DELTA_BASE = f"{_GRAPH}/me/mailFolders/inbox/messages/delta"


async def run_mail_delta_sync(
    app_session: AsyncSession,
    it: Integration,
) -> dict[str, Any]:
    """Inbox message delta, then one ``email.thread`` per conversation snapshot (idempotent)."""
    s = get_settings()
    if not (s.m365_oauth_client_id or s.oidc_client_id) or not (s.m365_oauth_client_secret or s.oidc_client_secret):
        raise ValueError("M365 OAuth is not configured")
    if it.provider != "m365_mail":
        raise ValueError("integration is not m365_mail")
    tid = it.tenant_id
    c0 = _cfg_dict(it.config or {})
    g0 = _cfg_dict(c0.get("graph") or {})
    d_raw = g0.get("mail_delta_link")
    delta_stored: str | None = d_raw if isinstance(d_raw, str) else None
    o0 = _cfg_dict(c0.get("oauth") or {})
    if not o0.get("refresh_token"):
        raise ValueError("integration has no OAuth tokens; run /connect first")
    issuer = (s.m365_oauth_issuer or s.oidc_issuer or "").strip()
    if not issuer:
        raise ValueError("issuer not configured")

    inserted = 0
    new_delta: str | None = None
    conv_seen: set[str] = set()
    first_delta = not bool(delta_stored)
    next_url: str | None = delta_stored

    async with httpx.AsyncClient(timeout=60.0) as gclient:
        meta = await fetch_metadata(gclient, issuer)
        atok = await _ensure_access_token(gclient, meta, it, s)
        await app_session.flush()

        while next_url is not None or first_delta:
            u = str(next_url) if next_url else INBOX_DELTA_BASE
            is_initial = (not next_url) and first_delta
            p_req: dict[str, str] | None = (
                {"$select": _MAIL_SELECT} if is_initial and not delta_stored else None
            )
            r = await _graph_get(gclient, u, auth=atok, params=p_req)
            first_delta = False

            if r.status_code == 401:
                atok = await _ensure_access_token(gclient, meta, it, s)
                await app_session.flush()
                r = await _graph_get(gclient, u, auth=atok, params=p_req)

            if r.is_error:
                _LOG.warning("graph mail delta failed: %s %s", r.status_code, r.text[:300])
                raise ValueError(f"Graph error: {r.status_code}")

            page: dict[str, Any] = r.json()
            for itm in page.get("value") or []:
                if not isinstance(itm, dict) or itm.get("@removed"):
                    continue
                mid = itm.get("id")
                conv = itm.get("conversationId")
                if isinstance(conv, str) and conv:
                    conv_seen.add(conv)
                elif isinstance(mid, str) and mid:
                    conv_seen.add(f"__msg__{mid}")

            dlink = page.get("@odata.deltaLink")
            if isinstance(dlink, str) and dlink:
                new_delta = dlink
            nxt = page.get("@odata.nextLink")
            if isinstance(nxt, str) and nxt:
                next_url = nxt
            else:
                next_url = None

        for conv in conv_seen:
            if conv.startswith("__msg__"):
                mid = conv[7:]
                enc = quote(mid, safe="")
                rone = await _graph_get(
                    gclient, f"{_GRAPH}/me/messages/{enc}", auth=atok, params={"$select": _MAIL_SELECT}
                )
                if rone.is_error or rone.status_code == 404:
                    continue
                mone = rone.json()
                if not isinstance(mone, dict):
                    continue
                msgs: list[dict[str, Any]] = [mone]
                cid = str(mone.get("conversationId") or mid)
            else:
                msgs = await _list_thread_messages_paged(gclient, auth=atok, conv=conv)
                if not msgs:
                    _LOG.warning("thread list empty: conversation %s", conv[:80])
                    continue
                cid = str(msgs[0].get("conversationId") or conv)
            msgs = sorted(msgs, key=_message_sort_key)
            clean_ids = sorted([i for i in (str(m.get("id") or "") for m in msgs) if i])
            if not clean_ids:
                continue
            source_ref = _source_ref_for_thread(cid, clean_ids)
            async with tenant_session(tid) as t0:
                if await _source_ref_exists(t0, tenant_id=tid, source_ref=source_ref):
                    continue
            out_msgs: list[dict[str, Any]] = []
            subj = str(msgs[0].get("subject") or "")
            last_sent: datetime = datetime.now(_UTC)
            for m in msgs:
                m_id = str(m.get("id") or "")
                if not m_id:
                    continue
                body_txt = _body_text(m.get("body"))
                bref = await store_email_body(tenant_id=tid, message_id=m_id, content=body_txt)
                to_list: list[str] = []
                for r in m.get("toRecipients") or []:
                    a = _addr_from_recipient(r)
                    if a:
                        to_list.append(a)
                fr = _addr_from_recipient(m.get("from")) or ""
                st = str(m.get("sentDateTime") or "")
                if st:
                    try:
                        last_sent = _parse_graph_dt(st)
                    except ValueError:
                        pass
                out_msgs.append(
                    {
                        "from": fr,
                        "to": to_list,
                        "sent_at": st,
                        "body_ref": bref,
                    }
                )
            payload: dict[str, Any] = {
                "thread_id": cid,
                "subject": subj,
                "participants": _collect_participants(msgs),
                "messages": out_msgs,
            }
            async with tenant_session(tid) as t_sess:
                if await _source_ref_exists(t_sess, tenant_id=tid, source_ref=source_ref):
                    continue
                t_sess.add(
                    CanonicalMemoryEvent(
                        tenant_id=tid,
                        event_type="email.thread",
                        occurred_at=last_sent,
                        source_ref=source_ref,
                        payload=payload,
                    )
                )
                await t_sess.commit()
            inserted += 1

    conf = _cfg_dict(it.config or {})
    g2 = {**_cfg_dict(conf.get("graph") or {}), "mail_delta_link": new_delta or g0.get("mail_delta_link")}
    it.config = {
        **conf,
        "graph": g2,
        "graph_meta": {**_cfg_dict(conf.get("graph_meta") or {}), "last_mail_sync_at": time.time()},
    }
    await app_session.flush()
    return {"inserted": inserted, "delta_link": new_delta}
