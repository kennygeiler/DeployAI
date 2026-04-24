"""Map Slack event_callback payloads to ``slack.message`` canonical events."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from ingest.idempotency import canonical_ingestion_dedup_key
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.db import tenant_session
from control_plane.domain.integrations.models import Integration
from control_plane.infra.canonical_idempotent_write import try_insert_with_ingestion_dedup
from control_plane.infra.observability import log_ingest, observe_events_written

_LOG = logging.getLogger(__name__)


def _ts_to_dt(ts: str) -> datetime:
    try:
        f = float(ts)
        return datetime.fromtimestamp(f, tz=UTC)
    except (ValueError, OSError, OverflowError, TypeError):
        return datetime.now(UTC)


async def _integration_for_team(session: AsyncSession, *, team_id: str) -> Integration | None:
    r = await session.execute(select(Integration).where(Integration.provider == "slack"))
    for it in r.scalars().all():
        c = it.config or {}
        if not isinstance(c, dict):
            continue
        s = c.get("slack")
        if not isinstance(s, dict):
            continue
        if str(s.get("team_id") or "") == team_id:
            return it
    return None


async def process_slack_event_envelope(app_session: AsyncSession, *, data: dict[str, Any]) -> dict[str, Any]:
    """Handle ``event_callback`` only; caller handles URL challenge and signature."""
    if str(data.get("type") or "") != "event_callback":
        return {"action": "ignore", "reason": "not_event_callback"}
    team_id = str(data.get("team_id") or (data.get("authorizations") or [{}])[0].get("team_id") or "")
    if not team_id:
        _LOG.warning("slack event missing team_id")
        return {"action": "ignore", "reason": "no_team_id"}
    it = await _integration_for_team(app_session, team_id=team_id)
    if it is None:
        log_ingest("slack_event_unknown_team", team_id=team_id)
        return {"action": "ok", "reason": "unknown_team"}
    ev = data.get("event")
    if not isinstance(ev, dict):
        return {"action": "ok", "reason": "no_event"}
    ev_t = str(ev.get("type") or "")
    if ev_t != "message":
        return {"action": "ok", "reason": f"event_type={ev_t}"}
    st = ev.get("subtype")
    if isinstance(st, str) and st in ("bot_message", "message_changed", "message_deleted", "message_replied"):
        return {"action": "ok", "reason": f"subtype={st}"}
    if ev.get("bot_id") and st != "file_share":
        return {"action": "ok", "reason": "bot_message"}
    ch = str(ev.get("channel") or "")
    u_ts = str(ev.get("ts") or "")
    if not ch or not u_ts:
        return {"action": "ok", "reason": "incomplete_message"}
    txt = str(ev.get("text") or "")
    uid = str(ev.get("user") or "")
    thread = str(ev.get("thread_ts") or "")
    tid = it.tenant_id
    source_ref = f"slack:msg:{ch}:{u_ts}"
    dedup = canonical_ingestion_dedup_key(provider="slack", source_id=f"msg:{ch}:{u_ts}", version="v1")
    occ = _ts_to_dt(u_ts)
    payload: dict[str, Any] = {
        "session_unit": "slack.message",
        "team_id": team_id,
        "channel": ch,
        "user": uid,
        "text": txt[:20000],
        "thread_ts": thread or None,
    }
    async with tenant_session(tid) as t_sess:
        ok = await try_insert_with_ingestion_dedup(
            t_sess,
            tenant_id=tid,
            event_type="slack.message",
            occurred_at=occ,
            source_ref=source_ref,
            payload=payload,
            ingestion_dedup_key=dedup,
        )
        if ok:
            observe_events_written("slack", 1)
            log_ingest("slack_message_ingested", team_id=team_id, channel=ch, ts=u_ts)
        await t_sess.commit()
    return {"action": "ingested" if ok else "deduped", "ingested": bool(ok)}
