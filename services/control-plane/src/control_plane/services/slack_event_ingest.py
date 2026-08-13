"""Channel-scoped Slack intake (Wave 5 SL1).

Consent model: inviting the DeployAI bot to a channel is the consent
boundary; a ``slack_channel_mappings`` row (channel → engagement) is the
strategist's explicit opt-in. Behavior per event:

- ``message`` in an actively **mapped** channel → one ``slack_staging_messages``
  row (idempotent on ``(tenant, channel, ts)`` so Slack re-delivery is safe).
  Canonical ``slack.thread`` snapshots are batched later by
  :mod:`control_plane.services.slack_snapshot_flush` — nothing canonical is
  written at event time.
- ``message`` in an **unmapped** channel → counted + dropped. No storage.
- ``member_joined_channel`` for the bot user in an unmapped channel → one
  ``slack_pending_channels`` row (channel id + best-effort name only, never
  content) so the settings UI can offer the channel for mapping.

Caller (``/integrations/slack/events``) handles URL challenge + signature.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

import httpx
from prometheus_client import Counter
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.db import tenant_session
from control_plane.domain.integrations.models import Integration
from control_plane.domain.slack_intake import (
    SlackChannelMapping,
    SlackPendingChannel,
    SlackStagingMessage,
)
from control_plane.infra.observability import log_ingest
from control_plane.integrations.slack_oauth import fetch_slack_channel_name

_LOG = logging.getLogger(__name__)

SLACK_UNMAPPED_DROPPED: Counter = Counter(
    "deployai_slack_unmapped_events_dropped_total",
    "Slack message events dropped because the channel has no engagement mapping (consent boundary).",
    ("team_id",),
)

# Message subtypes that never reach staging (edits/deletes would mutate a
# snapshot; the ledger is append-only — a re-batched snapshot is the only
# way content changes, and we deliberately do not ingest edits).
_SKIPPED_SUBTYPES = ("bot_message", "message_changed", "message_deleted", "message_replied")


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


def _bot_user_id(it: Integration) -> str:
    c = it.config if isinstance(it.config, dict) else {}
    oauth = c.get("oauth")
    if not isinstance(oauth, dict):
        return ""
    return str(oauth.get("bot_user_id") or "")


def _bot_token(it: Integration) -> str:
    c = it.config if isinstance(it.config, dict) else {}
    oauth = c.get("oauth")
    if not isinstance(oauth, dict):
        return ""
    return str(oauth.get("access_token") or "")


async def _active_mapping(t_sess: AsyncSession, *, tenant_id: Any, channel_id: str) -> SlackChannelMapping | None:
    r = await t_sess.execute(
        select(SlackChannelMapping).where(
            SlackChannelMapping.tenant_id == tenant_id,
            SlackChannelMapping.channel_id == channel_id,
            SlackChannelMapping.revoked_at.is_(None),
        )
    )
    return r.scalar_one_or_none()


async def _handle_message(it: Integration, *, team_id: str, ev: dict[str, Any]) -> dict[str, Any]:
    st = ev.get("subtype")
    if isinstance(st, str) and st in _SKIPPED_SUBTYPES:
        return {"action": "ok", "reason": f"subtype={st}"}
    if ev.get("bot_id") and st != "file_share":
        return {"action": "ok", "reason": "bot_message"}
    ch = str(ev.get("channel") or "")
    u_ts = str(ev.get("ts") or "")
    if not ch or not u_ts:
        return {"action": "ok", "reason": "incomplete_message"}
    tid = it.tenant_id
    async with tenant_session(tid) as t_sess:
        mapping = await _active_mapping(t_sess, tenant_id=tid, channel_id=ch)
        if mapping is None:
            # Consent boundary: no mapping → count and drop, never store.
            SLACK_UNMAPPED_DROPPED.labels(team_id or "unknown").inc()
            log_ingest("slack_unmapped_dropped", team_id=team_id, channel=ch)
            return {"action": "dropped", "reason": "unmapped_channel"}
        ins = (
            insert(SlackStagingMessage)
            .values(
                tenant_id=tid,
                channel_id=ch,
                message_ts=u_ts,
                thread_ts=str(ev.get("thread_ts") or "") or None,
                user_id=str(ev.get("user") or ""),
                text_body=str(ev.get("text") or "")[:20000],
                team_id=team_id,
                occurred_at=_ts_to_dt(u_ts),
            )
            .on_conflict_do_nothing(constraint="uq_slack_staging_messages_msg")
            .returning(SlackStagingMessage.id)
        )
        r = await t_sess.execute(ins)
        staged = r.fetchone() is not None
        if staged:
            log_ingest("slack_message_staged", team_id=team_id, channel=ch, ts=u_ts)
        await t_sess.commit()
    return {"action": "staged" if staged else "deduped", "staged": staged}


async def _handle_member_joined(it: Integration, *, team_id: str, ev: dict[str, Any]) -> dict[str, Any]:
    joined_user = str(ev.get("user") or "")
    bot_uid = _bot_user_id(it)
    if not bot_uid or joined_user != bot_uid:
        return {"action": "ok", "reason": "not_bot_join"}
    ch = str(ev.get("channel") or "")
    if not ch:
        return {"action": "ok", "reason": "no_channel"}
    tid = it.tenant_id
    # Best-effort channel name for the settings UI; the pending row stores
    # id + name only, never content, so failure here degrades to an id-only row.
    name = ""
    token = _bot_token(it)
    if token:
        try:
            async with httpx.AsyncClient() as h:
                name = await fetch_slack_channel_name(h, token=token, channel_id=ch)
        except (httpx.HTTPError, ValueError):
            _LOG.info("slack conversations.info failed for %s; pending row keeps empty name", ch)
    async with tenant_session(tid) as t_sess:
        mapping = await _active_mapping(t_sess, tenant_id=tid, channel_id=ch)
        if mapping is not None:
            return {"action": "ok", "reason": "already_mapped"}
        ins = (
            insert(SlackPendingChannel)
            .values(tenant_id=tid, channel_id=ch, channel_name=name)
            .on_conflict_do_nothing(constraint="uq_slack_pending_channels_channel")
        )
        await t_sess.execute(ins)
        await t_sess.commit()
    log_ingest("slack_pending_channel", team_id=team_id, channel=ch)
    return {"action": "pending_channel", "channel": ch}


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
    if ev_t == "message":
        return await _handle_message(it, team_id=team_id, ev=ev)
    if ev_t == "member_joined_channel":
        return await _handle_member_joined(it, team_id=team_id, ev=ev)
    return {"action": "ok", "reason": f"event_type={ev_t}"}
