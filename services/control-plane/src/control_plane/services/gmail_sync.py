"""Gmail thread → canonical ``email.thread`` (idempotent, FR10/FR18)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import time
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import httpx
from ingest.idempotency import canonical_ingestion_dedup_key
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.settings import get_settings
from control_plane.db import tenant_session
from control_plane.domain.integrations.models import Integration
from control_plane.infra.canonical_idempotent_write import try_insert_with_ingestion_dedup
from control_plane.infra.email_body_store import store_email_body
from control_plane.integrations.gmail_oauth import gmail_oauth_creds, refresh_gmail_access

_LOG = logging.getLogger(__name__)
_GMAIL = "https://gmail.googleapis.com/gmail/v1"


def _cfg(x: object) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _b64url_decode(data: str) -> str:
    pad = (4 - len(data) % 4) % 4
    b = data + ("=" * pad)
    try:
        return base64.urlsafe_b64decode(b.encode("ascii")).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _body_from_payload(payload: dict[str, Any]) -> str:
    body = payload.get("body") or {}
    if isinstance(body, dict) and body.get("data"):
        return _b64url_decode(str(body["data"]))
    for part in payload.get("parts") or []:
        if not isinstance(part, dict):
            continue
        mime = str(part.get("mimeType") or "")
        if mime == "text/plain" and part.get("data"):
            return _b64url_decode(str(part["data"]))
    for part in payload.get("parts") or []:
        if not isinstance(part, dict):
            continue
        inner = part.get("payload")
        if isinstance(inner, dict):
            s = _body_from_payload(inner)
            if s:
                return s
        for sub in part.get("parts") or []:
            if isinstance(sub, dict) and str(sub.get("mimeType") or "") == "text/plain" and sub.get("data"):
                return _b64url_decode(str(sub["data"]))
    return ""


def _header_map(payload: dict[str, Any]) -> dict[str, str]:
    m: dict[str, str] = {}
    h = payload.get("headers")
    if not isinstance(h, list):
        return m
    for he in h:
        if not isinstance(he, dict):
            continue
        n, v = he.get("name"), he.get("value")
        if isinstance(n, str) and isinstance(v, str):
            m[n.lower()] = v
    return m


def _split_addr_line(s: str) -> list[str]:
    return [p.strip() for p in s.replace("\n", " ").split(",") if p.strip()]


def _fp_from_ids(ids: list[str]) -> str:
    h = hashlib.sha256("|".join(sorted(ids)).encode("utf-8")).hexdigest()[:20]
    return h


def _source_ref(thread_id: str, fp: str) -> str:
    return f"gmail:email_thread:{thread_id}@{fp}"


async def _ensure_access(
    client: httpx.AsyncClient,
    it: Integration,
    creds: tuple[str, str, str],
) -> str:
    client_id, client_secret, _ = creds
    c = _cfg(it.config)
    oauth = _cfg(c.get("oauth"))
    at = oauth.get("access_token")
    at_s = at if isinstance(at, str) else None
    exp = float(oauth.get("expires_at_epoch") or 0)
    rt = oauth.get("refresh_token")
    if at_s and time.time() < exp - 60:
        return at_s
    if not isinstance(rt, str) or not rt:
        raise ValueError("Gmail integration has no refresh_token; reconnect OAuth with consent")
    new_t = await refresh_gmail_access(client, client_id=client_id, client_secret=client_secret, refresh_token=rt)
    at2 = str(new_t.get("access_token") or "")
    if not at2:
        raise ValueError("Gmail token response missing access_token")
    ex_in = int(new_t.get("expires_in") or 3600)
    new_rt = new_t.get("refresh_token", rt)
    if not isinstance(new_rt, str):
        new_rt = rt
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


async def _gget(
    client: httpx.AsyncClient,
    url: str,
    *,
    auth: str,
) -> httpx.Response:
    r = await client.get(url, headers={"Authorization": f"Bearer {auth}"}, timeout=60.0)
    return r


async def run_gmail_inbox_sync(
    app_session: AsyncSession,
    it: Integration,
) -> dict[str, Any]:
    """List recent INBOX messages, group by thread, write one ``email.thread`` per thread snapshot."""
    s = get_settings()
    creds = gmail_oauth_creds(s)
    if not creds:
        raise ValueError("Gmail OAuth is not configured (set DEPLOYAI_GOOGLE_GMAIL_* in settings)")
    if it.provider != "google_gmail":
        raise ValueError("integration is not google_gmail")
    tid = it.tenant_id
    o0 = _cfg(_cfg(it.config).get("oauth"))
    if not o0.get("refresh_token"):
        raise ValueError("integration has no OAuth tokens; run /connect first")

    inserted = 0
    gconf = _cfg(_cfg(it.config).get("gmail"))
    last_hist = gconf.get("last_history_id")
    _ = last_hist  # reserved for future history.list incrementals

    async with httpx.AsyncClient(timeout=60.0) as h:
        atok = await _ensure_access(h, it, creds)
        await app_session.flush()
        r = await _gget(h, f"{_GMAIL}/users/me/messages?maxResults=50&labelIds=INBOX", auth=atok)
        if r.status_code == 401:
            atok = await _ensure_access(h, it, creds)
            await app_session.flush()
            r = await _gget(h, f"{_GMAIL}/users/me/messages?maxResults=50&labelIds=INBOX", auth=atok)
        if r.is_error:
            raise ValueError(f"Gmail messages.list: {r.status_code} {r.text[:200]}")
        mlist: dict[str, Any] = r.json()
        ids: list[dict[str, str]] = []
        for m in mlist.get("value") or []:
            if not isinstance(m, dict):
                continue
            i, th = m.get("id"), m.get("threadId")
            if isinstance(i, str) and i and isinstance(th, str) and th:
                ids.append({"id": i, "threadId": th})
        by_thread: dict[str, set[str]] = {}
        for row in ids:
            by_thread.setdefault(row["threadId"], set()).add(row["id"])
        p = await _gget(h, f"{_GMAIL}/users/me/profile", auth=atok)
        profile_hid: str | None = None
        if p.status_code == 200:
            pj = p.json()
            if isinstance(pj, dict) and isinstance(pj.get("historyId"), str):
                profile_hid = str(pj["historyId"])

        for thread_id, _ids in list(by_thread.items())[:30]:
            await asyncio.sleep(0.05)
            tr = await _gget(h, f"{_GMAIL}/users/me/threads/{thread_id}?format=full", auth=atok)
            if tr.status_code == 401:
                atok = await _ensure_access(h, it, creds)
                await app_session.flush()
                tr = await _gget(h, f"{_GMAIL}/users/me/threads/{thread_id}?format=full", auth=atok)
            if tr.is_error and tr.status_code != 404:
                _LOG.warning("gmail thread get failed: %s %s", tr.status_code, tr.text[:120])
                continue
            if tr.status_code != 200:
                continue
            tj: dict[str, Any] = tr.json()
            msgs_raw = tj.get("messages") or []
            clean_ids = sorted({str(m.get("id") or "") for m in msgs_raw if isinstance(m, dict) and m.get("id")})
            if not clean_ids:
                continue
            fp = _fp_from_ids(clean_ids)
            source_ref = _source_ref(thread_id, fp)
            out_msgs: list[dict[str, Any]] = []
            last_sent = datetime.now(UTC)
            for m in msgs_raw:
                if not isinstance(m, dict):
                    continue
                mid = str(m.get("id") or "")
                if not mid:
                    continue
                pld = m.get("payload")
                pay = pld if isinstance(pld, dict) else {}
                body_txt = _body_from_payload(pay)
                bref = await store_email_body(tenant_id=tid, message_id=f"gmail-{mid}", content=body_txt)
                hmap = _header_map(pay)
                to_list = _split_addr_line(hmap.get("to", ""))
                fr = hmap.get("from", "")
                st = hmap.get("date") or ""
                if st:
                    try:
                        dt = parsedate_to_datetime(st)
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=UTC)
                        last_sent = dt
                    except Exception:
                        pass
                out_msgs.append(
                    {
                        "from": fr,
                        "to": to_list,
                        "sent_at": st,
                        "body_ref": bref,
                    }
                )
            subj = ""
            for m in msgs_raw:
                if not isinstance(m, dict):
                    continue
                pld = m.get("payload")
                pay = pld if isinstance(pld, dict) else {}
                hmap2 = _header_map(pay)
                s0 = hmap2.get("subject", "")
                if s0:
                    subj = s0
                    break
            part_set: set[str] = set()
            for m in out_msgs:
                for x in m.get("to") or []:
                    part_set.add(x)
                a = m.get("from")
                if isinstance(a, str) and a:
                    part_set.add(a)
            payload: dict[str, Any] = {
                "thread_id": thread_id,
                "subject": subj,
                "participants": sorted(part_set),
                "messages": out_msgs,
                "provider": "gmail",
            }
            dedup = canonical_ingestion_dedup_key(
                provider="gmail", source_id=f"email_thread:{thread_id}:{fp}", version="v1"
            )
            async with tenant_session(tid) as t_sess:
                ok = await try_insert_with_ingestion_dedup(
                    t_sess,
                    tenant_id=tid,
                    event_type="email.thread",
                    occurred_at=last_sent,
                    source_ref=source_ref,
                    payload=payload,
                    ingestion_dedup_key=dedup,
                )
                if ok:
                    inserted += 1
                await t_sess.commit()

    g2 = {**_cfg(_cfg(it.config).get("gmail") or {}), "last_full_sync_at": time.time()}
    if profile_hid:
        g2["last_history_id"] = profile_hid
    conf = _cfg(it.config)
    it.config = {**conf, "gmail": g2}
    await app_session.flush()
    return {"inserted": inserted, "history_id": profile_hid}
