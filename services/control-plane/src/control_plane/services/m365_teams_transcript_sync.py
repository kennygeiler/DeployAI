"""M365 / Teams online meeting → transcript VTT (Epic 3 Story 3-3, FR11)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
import uuid
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.settings import ControlPlaneSettings, get_settings
from control_plane.db import tenant_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.identity import IdentityNode
from control_plane.domain.integrations.models import Integration
from control_plane.infra.transcript_artifact_store import store_transcript_vtt
from control_plane.integrations.m365_oauth import GRAPH_TEAMS_SCOPES, fetch_metadata, refresh_delegation_access

_LOG = logging.getLogger(__name__)
_GRAPH = "https://graph.microsoft.com/v1.0"
_VTT_SPK = re.compile(r"<v\s+([^>]+)>")


def _cfg_dict(x: object) -> dict[str, Any]:
    return x if isinstance(x, dict) else {}


def _email_hash_16(email: str) -> str:
    n = email.strip().lower()
    return hashlib.sha256(n.encode("utf-8")).hexdigest()[:16]


def _parse_graph_dt(s: str | None) -> datetime | None:
    if not s or not isinstance(s, str):
        return None
    s2 = s.strip()
    if s2.endswith("Z"):
        return datetime.fromisoformat(s2.replace("Z", "+00:00")).astimezone(UTC)
    if len(s2) > 10 and s2[-6] in "+-":
        return datetime.fromisoformat(s2).astimezone(UTC)
    try:
        return datetime.fromisoformat(s2 + "+00:00").astimezone(UTC)
    except ValueError:
        return None


def _event_start_end_minutes(ev: dict[str, Any]) -> tuple[datetime | None, datetime | None, float]:
    s = ev.get("start")
    e = ev.get("end")
    sdt = _parse_graph_dt(
        s.get("dateTime") if isinstance(s, dict) and isinstance(s.get("dateTime"), str) else None
    )
    edt = _parse_graph_dt(
        e.get("dateTime") if isinstance(e, dict) and isinstance(e.get("dateTime"), str) else None
    )
    if sdt and edt:
        return sdt, edt, max(0.0, (edt - sdt).total_seconds() / 60.0)
    return sdt, edt, 0.0


def _vtt_speaker_names(vtt: str) -> list[str]:
    return sorted({m.strip() for m in _VTT_SPK.findall(vtt)})


def _chunk_vtt_cues(vtt: str, duration_mins: float) -> list[str]:
    if duration_mins < 60.0:
        return [vtt]
    parts = re.split(r"\n\n+", vtt.strip())
    if len(parts) < 2:
        return [vtt]
    n = min(8, max(2, int(duration_mins // 15) or 2))
    chunk_size = max(1, (len(parts) + n - 1) // n)
    out: list[str] = []
    i = 0
    while i < len(parts):
        block = "\n\n".join(parts[i : i + chunk_size])
        if block:
            out.append(block)
        i += chunk_size
    return out or [vtt]


def _attendees_struct(ev: dict[str, Any]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for a in ev.get("attendees") or []:
        if not isinstance(a, dict):
            continue
        ea = a.get("emailAddress")
        if not isinstance(ea, dict):
            continue
        ad = ea.get("address")
        nm = ea.get("name")
        if isinstance(ad, str) and ad:
            e_l = ad.strip().lower()
            out.append(
                {
                    "email": e_l,
                    "name": str(nm) if isinstance(nm, str) else "",
                }
            )
    return out


async def _source_ref_exists(
    t_session: AsyncSession, *, tenant_id: uuid.UUID, source_ref: str
) -> bool:
    r = await t_session.execute(
        select(CanonicalMemoryEvent.id).where(
            CanonicalMemoryEvent.tenant_id == tenant_id,
            CanonicalMemoryEvent.source_ref == source_ref,
        )
    )
    return r.scalar_one_or_none() is not None


async def _match_emails_to_identities(
    t_session: AsyncSession, *, tenant_id: uuid.UUID, emails: list[str]
) -> dict[str, str]:
    if not emails:
        return {}
    h_by_email = {_email_hash_16(e): e for e in emails}
    hvals = list(h_by_email.keys())
    r = await t_session.execute(
        select(IdentityNode).where(
            IdentityNode.tenant_id == tenant_id,
            IdentityNode.primary_email_hash.in_(hvals),
        )
    )
    by_email: dict[str, str] = {}
    for node in r.scalars().all():
        h = str(node.primary_email_hash)
        em = h_by_email.get(h)
        if em:
            by_email[em] = str(node.id)
    return by_email


async def _graph_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    auth: str,
    params: Mapping[str, str] | None = None,
) -> httpx.Response:
    h = {"Authorization": f"Bearer {auth}", "Prefer": "odata.maxpagesize=25"}
    r = await client.get(str(url), headers=h, params=params, timeout=90.0)
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
        r = await client.get(str(url), headers=h, params=params, timeout=90.0)
    return r


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
        scope=GRAPH_TEAMS_SCOPES,
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


def _first_delta_url() -> str:
    now = datetime.now(UTC)
    start = (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = (now + timedelta(days=90)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return f"{_GRAPH}/me/calendarView/delta?startDateTime={start}&endDateTime={end}"


def _filter_join_web_url(ju: str) -> str:
    enc = quote(ju, safe="")
    return f"JoinWebUrl eq '{enc}'"


def _transcript_list_sorted(transcripts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(t: dict[str, Any]) -> str:
        return str(t.get("endDateTime") or t.get("createdDateTime") or "")

    return sorted(transcripts, key=key, reverse=True)


async def _fetch_transcript_vtt(
    gclient: httpx.AsyncClient,
    *,
    auth: str,
    meeting_id: str,
    transcript_id: str,
) -> str:
    m_enc = quote(meeting_id, safe="")
    t_enc = quote(transcript_id, safe="")
    u = f"{_GRAPH}/me/onlineMeetings/{m_enc}/transcripts/{t_enc}/content"
    r = await _graph_get(gclient, u, auth=auth, params={"$format": "text/vtt"})
    if r.is_error:
        _LOG.warning("transcript content failed: %s", r.status_code)
        return ""
    return r.text or ""


async def _ingest_event_transcripts(
    gclient: httpx.AsyncClient,
    *,
    auth: str,
    ev: dict[str, Any],
    tenant_id: uuid.UUID,
) -> int:
    if not ev.get("isOnlineMeeting"):
        return 0
    om = ev.get("onlineMeeting")
    if not isinstance(om, dict):
        return 0
    ju = om.get("joinUrl")
    if not isinstance(ju, str) or not ju:
        return 0
    eid = ev.get("id")
    eid = str(eid) if eid else ""
    _, end_dt, _dur_m = _event_start_end_minutes(ev)
    if not end_dt or end_dt > datetime.now(UTC):
        return 0

    flt = _filter_join_web_url(ju)
    r0 = await _graph_get(
        gclient, f"{_GRAPH}/me/onlineMeetings", auth=auth, params={"$filter": flt}
    )
    if r0.is_error or r0.status_code not in (200, 204):
        return 0
    data0: dict[str, Any] = r0.json()
    oms: list[dict[str, Any]] = [x for x in (data0.get("value") or []) if isinstance(x, dict)]
    if not oms:
        return 0
    meeting_id = str(oms[0].get("id") or "")
    if not meeting_id:
        return 0
    m_seg = quote(meeting_id, safe="")
    r1 = await _graph_get(
        gclient, f"{_GRAPH}/me/onlineMeetings/{m_seg}/transcripts", auth=auth, params={}
    )
    if r1.is_error or r1.status_code != 200:
        return 0
    tj: dict[str, Any] = r1.json()
    trows = [x for x in tj.get("value") or [] if isinstance(x, dict) and x.get("id")]
    if not trows:
        return 0
    pick = _transcript_list_sorted(trows)[0]
    tid = str(pick.get("id") or "")
    if not tid:
        return 0
    source_ref = f"graph:meeting_transcript:{tid}"
    async with tenant_session(tenant_id) as t0:
        if await _source_ref_exists(t0, tenant_id=tenant_id, source_ref=source_ref):
            return 0

    vtt = await _fetch_transcript_vtt(
        gclient, auth=auth, meeting_id=meeting_id, transcript_id=tid
    )
    if not vtt.strip():
        return 0
    sdt, edt, dmin = _event_start_end_minutes(ev)
    occ = edt or datetime.now(UTC)
    vtt_pieces = _chunk_vtt_cues(vtt, dmin)
    approx = dmin / max(1, len(vtt_pieces)) if dmin else 0.0
    chunks: list[dict[str, Any]] = []
    for i, part in enumerate(vtt_pieces):
        aid = f"{tid}-part-{i}"
        ref = await store_transcript_vtt(
            tenant_id=tenant_id, artifact_id=aid, content=part
        )
        chunks.append(
            {
                "index": i,
                "approx_minutes": round(approx, 1),
                "transcript_ref": ref,
            }
        )
    at_list = _attendees_struct(ev)
    em_list = [a["email"] for a in at_list]
    vtt_names = _vtt_speaker_names(vtt)
    name_set = {a.get("name", "").lower() for a in at_list if a.get("name")}
    id_map: dict[str, str] = {}
    part_struct: list[dict[str, Any]] = []
    async with tenant_session(tenant_id) as t_id:
        id_map = await _match_emails_to_identities(
            t_id, tenant_id=tenant_id, emails=em_list
        )
    for a in at_list:
        part_struct.append(
            {
                "email": a.get("email", ""),
                "name": a.get("name", ""),
                "identity_id": id_map.get(a.get("email", "")),
            }
        )
    cands: list[dict[str, str]] = [
        {"label": lab} for lab in vtt_names if lab.strip().lower() not in name_set
    ]

    payload: dict[str, Any] = {
        "session_unit": "meeting.transcript",
        "calendar_event_id": eid,
        "online_meeting_id": meeting_id,
        "transcript_id": tid,
        "subject": str(ev.get("subject") or ""),
        "i_cal_uid": str(ev.get("iCalUId") or "") or None,
        "started_at": sdt.isoformat() if sdt else None,
        "ended_at": edt.isoformat() if edt else None,
        "duration_minutes": round(dmin, 1),
        "transcript_format": "text/vtt",
        "transcript_chunks": chunks,
        "participants": part_struct,
        "identity_resolution_candidates": cands,
    }
    async with tenant_session(tenant_id) as t_sess:
        if await _source_ref_exists(t_sess, tenant_id=tenant_id, source_ref=source_ref):
            return 0
        t_sess.add(
            CanonicalMemoryEvent(
                tenant_id=tenant_id,
                event_type="meeting.transcript",
                occurred_at=occ,
                source_ref=source_ref,
                payload=payload,
            )
        )
        await t_sess.commit()
    return 1


async def run_teams_transcript_sync(
    app_session: AsyncSession,
    it: Integration,
) -> dict[str, Any]:
    """Calendar delta for events with online meetings; fetch VTT; ``meeting.transcript`` (idempotent)."""
    s = get_settings()
    m_creds = s.m365_oauth_client_id or s.oidc_client_id
    m_sec = s.m365_oauth_client_secret or s.oidc_client_secret
    if not m_creds or not m_sec:
        raise ValueError("M365 OAuth is not configured")
    if it.provider != "m365_teams":
        raise ValueError("integration is not m365_teams")
    tid = it.tenant_id
    c0 = _cfg_dict(it.config or {})
    g0 = _cfg_dict(c0.get("graph") or {})
    dr = g0.get("teams_calendar_delta_link")
    delta_stored: str | None = dr if isinstance(dr, str) else None
    o0 = _cfg_dict(c0.get("oauth") or {})
    if not o0.get("refresh_token"):
        raise ValueError("integration has no OAuth tokens; run /connect first")
    issuer = (s.m365_oauth_issuer or s.oidc_issuer or "").strip()
    if not issuer:
        raise ValueError("issuer not configured")

    inserted = 0
    new_delta: str | None = None
    if delta_stored:
        next_url: str | None = delta_stored
    else:
        next_url = _first_delta_url()

    async with httpx.AsyncClient(timeout=90.0) as gclient:
        meta = await fetch_metadata(gclient, issuer)
        atok = await _ensure_access_token(gclient, meta, it, s)
        await app_session.flush()
        while next_url:
            r = await _graph_get(gclient, str(next_url), auth=atok, params=None)
            if r.status_code == 401:
                atok = await _ensure_access_token(gclient, meta, it, s)
                await app_session.flush()
                r = await _graph_get(gclient, str(next_url), auth=atok, params=None)
            if r.is_error:
                _LOG.warning("graph teams calendar failed: %s %s", r.status_code, r.text[:300])
                raise ValueError(f"Graph error: {r.status_code}")
            page: dict[str, Any] = r.json()
            for ev in page.get("value") or []:
                if not isinstance(ev, dict) or ev.get("@removed"):
                    continue
                if not ev.get("isOnlineMeeting"):
                    continue
                try:
                    n = await _ingest_event_transcripts(
                        gclient, auth=atok, ev=ev, tenant_id=tid
                    )
                except (ValueError, TypeError) as e:
                    _LOG.debug("skip event transcript: %s", e, exc_info=False)
                    continue
                inserted += n
            dlink = page.get("@odata.deltaLink")
            if isinstance(dlink, str) and dlink:
                new_delta = dlink
            nxt = page.get("@odata.nextLink")
            next_url = nxt if isinstance(nxt, str) else None

    conf = _cfg_dict(it.config or {})
    g2 = {
        **_cfg_dict(conf.get("graph") or {}),
        "teams_calendar_delta_link": new_delta or g0.get("teams_calendar_delta_link"),
    }
    it.config = {
        **conf,
        "graph": g2,
        "graph_meta": {**_cfg_dict(conf.get("graph_meta") or {}), "last_teams_transcript_sync_at": time.time()},
    }
    await app_session.flush()
    return {"inserted": inserted, "delta_link": new_delta}
