"""Batch staged Slack messages into ``slack.thread`` canonical snapshots (SL1).

Batching unit: per channel, per ``thread_ts`` when the messages are
threaded, else per UTC day. Each flush rebuilds the *whole* unit (all
staged messages for that channel + unit, flushed or not) and fingerprints
the sorted message timestamps — the same shape as the M365
``email.thread`` snapshots:

- Re-delivery / re-flush of the same message set → same fingerprint →
  same ``ingestion_dedup_key`` → deduped, no second row.
- New messages in a unit → new fingerprint → a **new** snapshot event.
  Snapshots are only ever superseded by new events, never mutated — the
  canonical ledger is append-only by trigger.

Consent: staged rows whose channel mapping was revoked since staging are
discarded (deleted, never flushed) — revocation withdraws consent for
anything not yet in the ledger.

Extraction chains on each newly written snapshot (best-effort, like the
BFF ``/ingest`` → ``/extract`` chain): the Cartographer proposes matrix
entities citing the snapshot event; failure never fails the flush.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import uuid
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from deployai_ingestlib.idempotency import canonical_ingestion_dedup_key
from llm_provider_py.types import LLMProvider
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.matrix_extractor import (
    ExistingNode,
    extract_matrix_proposals,
)
from control_plane.agents.matrix_extractor import (
    default_system_prompt as matrix_extractor_default_prompt,
)
from control_plane.agents.prompts import resolve_tenant_prompt
from control_plane.db import tenant_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.canonical_memory.matrix import MatrixNode, MatrixProposal
from control_plane.domain.canonical_memory.node_types import resolve_allowed_node_types
from control_plane.domain.slack_intake import SlackChannelMapping, SlackStagingMessage
from control_plane.infra.canonical_idempotent_write import insert_snapshot_with_ingestion_dedup
from control_plane.infra.observability import log_ingest, observe_events_written
from control_plane.ledger import emit_ledger_event
from control_plane.webhooks.dispatcher import dispatch as dispatch_webhook

_LOG = logging.getLogger(__name__)

SLACK_THREAD_EVENT_TYPE = "slack.thread"


def batch_unit_key(*, thread_ts: str | None, occurred_at: datetime) -> str:
    """Snapshot unit for one message: its thread, else its UTC day."""
    if thread_ts:
        return f"t{thread_ts}"
    return occurred_at.astimezone(UTC).strftime("d%Y-%m-%d")


def unit_fingerprint(message_ts: list[str]) -> str:
    """Stable fingerprint of a unit's message set (mirrors the email.thread shape)."""
    return hashlib.sha256(",".join(sorted(message_ts)).encode("utf-8")).hexdigest()[:20]


async def flush_tenant_slack_staging(
    *,
    tenant_id: uuid.UUID,
    llm: LLMProvider | None = None,
) -> dict[str, Any]:
    """Flush every channel with unflushed staged messages for one tenant.

    Returns ``{"snapshots_written", "deduped_units", "messages_flushed",
    "messages_discarded", "extraction_errors"}``.
    """
    written = 0
    deduped = 0
    flushed_msgs = 0
    discarded = 0
    extraction_errors: list[str] = []
    now = datetime.now(UTC)

    async with tenant_session(tenant_id) as t_sess:
        mrows = await t_sess.execute(
            select(SlackChannelMapping).where(
                SlackChannelMapping.tenant_id == tenant_id,
                SlackChannelMapping.revoked_at.is_(None),
            )
        )
        mappings = {m.channel_id: m for m in mrows.scalars().all()}

        srows = await t_sess.execute(select(SlackStagingMessage).where(SlackStagingMessage.tenant_id == tenant_id))
        staged = list(srows.scalars().all())

        # Consent withdrawal: staged content for revoked/never-mapped channels
        # is discarded, never flushed into the ledger.
        for row in staged:
            if row.channel_id not in mappings and row.flushed_at is None:
                await t_sess.delete(row)
                discarded += 1

        units: dict[tuple[str, str], list[SlackStagingMessage]] = defaultdict(list)
        for row in staged:
            if row.channel_id not in mappings:
                continue
            units[(row.channel_id, batch_unit_key(thread_ts=row.thread_ts, occurred_at=row.occurred_at))].append(row)

        for (channel_id, unit), rows in sorted(units.items()):
            if all(r.flushed_at is not None for r in rows):
                continue  # nothing new in this unit
            mapping = mappings[channel_id]
            rows = sorted(rows, key=lambda r: r.message_ts)
            ts_list = [r.message_ts for r in rows]
            fp = unit_fingerprint(ts_list)
            source_ref = f"slack:thread:{channel_id}:{unit}@{fp}"
            dedup = canonical_ingestion_dedup_key(
                provider="slack", source_id=f"thread:{channel_id}:{unit}:{fp}", version="v1"
            )
            payload: dict[str, Any] = {
                "session_unit": SLACK_THREAD_EVENT_TYPE,
                "team_id": rows[-1].team_id,
                "channel_id": channel_id,
                "channel_name": mapping.channel_name,
                "unit": unit,
                "thread_ts": rows[0].thread_ts,
                "participants": sorted({r.user_id for r in rows if r.user_id}),
                "messages": [{"user": r.user_id, "ts": r.message_ts, "text": r.text_body} for r in rows],
            }
            event_id = await insert_snapshot_with_ingestion_dedup(
                t_sess,
                tenant_id=tenant_id,
                engagement_id=mapping.engagement_id,
                event_type=SLACK_THREAD_EVENT_TYPE,
                occurred_at=rows[-1].occurred_at,
                source_ref=source_ref,
                payload=payload,
                ingestion_dedup_key=dedup,
            )
            for r in rows:
                if r.flushed_at is None:
                    r.flushed_at = now
                    flushed_msgs += 1
            if event_id is None:
                deduped += 1
                continue
            written += 1
            log_ingest("slack_thread_snapshot", channel=channel_id, unit=unit, fingerprint=fp)
            if llm is not None:
                try:
                    await _chain_extraction(
                        t_sess,
                        tenant_id=tenant_id,
                        engagement_id=mapping.engagement_id,
                        event_id=event_id,
                        llm=llm,
                    )
                except Exception as e:  # extraction is best-effort, flush must land
                    extraction_errors.append(f"{source_ref}: {e}")
                    _LOG.warning("slack flush: extraction failed for %s: %s", source_ref, e)
        await t_sess.commit()

    if written:
        observe_events_written("slack", written)
    return {
        "snapshots_written": written,
        "deduped_units": deduped,
        "messages_flushed": flushed_msgs,
        "messages_discarded": discarded,
        "extraction_errors": extraction_errors,
    }


async def _chain_extraction(
    t_sess: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    event_id: uuid.UUID,
    llm: LLMProvider,
) -> None:
    """Cartographer pass over one snapshot — the server-side mirror of the
    BFF ingest → extract chain (proposals + ledger + auto-accept + webhooks)."""
    # Route-module import: apply_proposal_auto_accept lives with the extract
    # route (historical location); importing here avoids duplicating the E4
    # policy. Deferred to call time to keep app import order untangled.
    from control_plane.api.routes.engagements_internal import apply_proposal_auto_accept

    event = (
        await t_sess.execute(
            select(CanonicalMemoryEvent).where(
                CanonicalMemoryEvent.tenant_id == tenant_id,
                CanonicalMemoryEvent.id == event_id,
            )
        )
    ).scalar_one()
    prompt = await resolve_tenant_prompt(t_sess, tenant_id, "cartographer", matrix_extractor_default_prompt())
    nodes = list(
        (await t_sess.execute(select(MatrixNode).where(MatrixNode.engagement_id == engagement_id))).scalars().all()
    )
    context = [ExistingNode(id=n.id, title=n.title, node_type=n.node_type) for n in nodes]
    allowed_node_types = await resolve_allowed_node_types(t_sess, tenant_id)
    drafts = await asyncio.to_thread(
        extract_matrix_proposals,
        event_id=event.id,
        event_source=event.event_type,
        event_occurred_at=event.occurred_at,
        event_payload=event.payload,
        existing_nodes=context,
        llm=llm,
        system_prompt=prompt,
        allowed_node_types=allowed_node_types,
    )
    created: list[MatrixProposal] = []
    for d in drafts:
        row = MatrixProposal(
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            source_event_id=event.id,
            proposal_kind=d.kind,
            payload=d.payload,
            rationale=d.rationale,
        )
        t_sess.add(row)
        created.append(row)
    if not created:
        return
    await t_sess.flush()
    for r in created:
        await emit_ledger_event(
            t_sess,
            tenant_id=tenant_id,
            engagement_id=engagement_id,
            occurred_at=datetime.now(UTC),
            actor_kind="agent:matrix_extractor",
            actor_id="cartographer",
            source_kind="llm_proposal_created",
            source_ref=r.id,
            summary=f"proposal drafted: {r.proposal_kind}"[:500],
            detail={
                "proposal_kind": r.proposal_kind,
                "source_event_id": str(r.source_event_id),
            },
        )
    await apply_proposal_auto_accept(
        t_sess,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        proposals=created,
    )
    for r in created:
        await dispatch_webhook(
            t_sess,
            tenant_id,
            "proposal.added",
            {
                "engagement_id": str(engagement_id),
                "proposal_id": str(r.id),
                "proposal_kind": r.proposal_kind,
                "source_event_id": str(r.source_event_id),
            },
        )
    await dispatch_webhook(
        t_sess,
        tenant_id,
        "extraction.completed",
        {
            "engagement_id": str(engagement_id),
            "event_id": str(event.id),
            "proposal_count": len(created),
        },
    )
