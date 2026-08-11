"""Disable an integration for real: revoke OAuth, purge queued work, delete stored secrets.

Pilot-refresh ticket A8 replaced the Epic 2 Story 2-6 stubs with working
phases. Each phase emits one ledger row (success or a distinct failure
kind) so an auditor can replay exactly what the kill switch did:

1. **OAuth revocation** (``killswitch_oauth_revoked`` /
   ``killswitch_oauth_revoke_failed``): provider-side token revocation via
   :mod:`control_plane.integrations.oauth_revocation`. Google revokes the
   refresh token; Slack revokes the bot token via ``auth.revoke``;
   Microsoft has no revocation endpoint for confidential-client refresh
   tokens, so the effective action is local token deletion (phase 3) plus
   a documented operator path (Graph ``invalidateAllRefreshTokens``).

2. **Queue purge** (``killswitch_queue_purged`` /
   ``killswitch_queue_purge_failed``): there is no SQS-backed
   per-integration queue in this deployment — the earlier SQS stub was
   aspirational and has been removed. The real queues are the
   ``embedding_jobs`` table (tenant-scoped; rows carry no integration id,
   so the purge is tenant-wide by design — a kill switch should err
   toward stopping work) and in-flight ``ingestion_runs`` for this
   integration, which are marked failed so the admin runs view shows the
   truncation honestly instead of a forever-"running" row.

3. **Secrets deletion** (``killswitch_secrets_deleted`` /
   ``killswitch_secrets_delete_failed``): the only per-integration
   secrets this codebase stores are the OAuth tokens in
   ``integrations.config["oauth"]`` (JSONB). That key is dropped
   entirely. Platform-level client ids/secrets live in process settings
   (env), are shared across tenants, and are out of scope here. No
   secrets-manager storage exists for integration credentials.

Provider failures never abort the kill switch: the integration is always
disabled and its stored tokens always deleted, with the failure recorded
in the ledger and surfaced in the return payload.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.domain.embedding_jobs import EmbeddingJob
from control_plane.domain.ingest_runs import IngestionRun
from control_plane.domain.integrations.models import Integration
from control_plane.integrations.oauth_revocation import RevocationResult, revoke_provider_tokens
from control_plane.ledger import emit_ledger_event
from control_plane.services.strategist_activity import append_strategist_activity

logger = logging.getLogger(__name__)

# Statuses that represent work not yet (fully) done. ``running`` embedding
# jobs are included: the worker marks them failed-safe on conflict, and a
# kill switch prefers a dropped job over a completed one.
_PENDING_EMBEDDING_STATUSES: tuple[str, ...] = ("queued", "running")


def _oauth_config(row: Integration) -> dict[str, Any]:
    cfg = row.config if isinstance(row.config, dict) else {}
    oauth = cfg.get("oauth")
    return oauth if isinstance(oauth, dict) else {}


async def _revoke_oauth(
    row: Integration,
    http_client: httpx.AsyncClient | None,
) -> RevocationResult:
    """Phase 1 — provider-side revocation of whatever tokens are stored."""
    oauth = _oauth_config(row)
    if http_client is not None:
        return await revoke_provider_tokens(http_client, provider=row.provider, oauth_config=oauth)
    async with httpx.AsyncClient() as client:
        return await revoke_provider_tokens(client, provider=row.provider, oauth_config=oauth)


async def _purge_queues(session: AsyncSession, row: Integration, *, now: datetime) -> dict[str, int]:
    """Phase 2 — drop pending embedding jobs; fail out in-flight ingestion runs.

    Returns counts for the ledger detail blob. See module docstring for
    why the embedding-job purge is tenant-wide.
    """
    jobs_res = await session.execute(
        delete(EmbeddingJob).where(
            EmbeddingJob.tenant_id == row.tenant_id,
            EmbeddingJob.status.in_(_PENDING_EMBEDDING_STATUSES),
        )
    )
    runs_res = await session.execute(
        update(IngestionRun)
        .where(
            IngestionRun.tenant_id == row.tenant_id,
            IngestionRun.integration == row.provider,
            IngestionRun.status == "running",
        )
        .values(
            status="failed",
            completed_at=now,
            error_count=1,
            error_summary={"message": "aborted by integration kill switch"},
        )
    )
    return {
        "embedding_jobs_deleted": int(getattr(jobs_res, "rowcount", 0) or 0),
        "ingestion_runs_aborted": int(getattr(runs_res, "rowcount", 0) or 0),
    }


def _delete_secrets(row: Integration) -> dict[str, Any]:
    """Phase 3 — drop the ``oauth`` blob (tokens) from the integration config.

    Non-secret config (Slack team metadata, Gmail history cursors, …)
    survives so a later reconnect starts from sane state. Returns the
    ledger detail blob.
    """
    cfg = dict(row.config) if isinstance(row.config, dict) else {}
    had_oauth = "oauth" in cfg
    cfg.pop("oauth", None)
    row.config = cfg
    return {"oauth_tokens_deleted": had_oauth, "storage": "integrations.config (DB)"}


async def disable_integration(
    session: AsyncSession,
    integration_id: uuid.UUID,
    *,
    actor_id: uuid.UUID | None = None,
    http_client: httpx.AsyncClient | None = None,
) -> dict[str, Any]:
    """Kill one integration: revoke, purge, delete secrets, disable, audit.

    ``http_client`` is injectable for tests; production callers omit it
    and a short-lived client is created per call.
    """
    r = await session.execute(select(Integration).where(Integration.id == integration_id).limit(1))
    row = r.scalar_one_or_none()
    if row is None:
        return {"not_found": True}
    if row.state == "disabled":
        return {"ok": True, "already_disabled": True, "integration_id": row.id, "tenant_id": row.tenant_id}

    now = datetime.now(UTC)
    actor = str(actor_id) if actor_id is not None else None

    # Phase 1 — OAuth revocation (must run before secrets deletion: it
    # needs the stored tokens). A provider failure is recorded, not fatal.
    try:
        revocation = await _revoke_oauth(row, http_client)
    except Exception as exc:  # defensive: helpers return results, but never let a bug block the kill
        logger.exception("integration.killswitch_oauth_revoke_error")
        revocation = RevocationResult(outcome="failed", note=f"unexpected error: {exc!r}")

    # Phase 2 — queue purge. Runs BEFORE any ledger emit: inserting a
    # ledger row enqueues an embedding job via the 0050 trigger, and the
    # kill switch's own audit rows should keep theirs.
    try:
        purge_counts = await _purge_queues(session, row, now=now)
        purge_ok = True
        purge_detail: dict[str, Any] = dict(purge_counts)
    except Exception as exc:
        logger.exception("integration.killswitch_queue_purge_error")
        purge_ok = False
        purge_detail = {"error": repr(exc)}

    await emit_ledger_event(
        session,
        tenant_id=row.tenant_id,
        engagement_id=None,
        occurred_at=now,
        actor_kind="user",
        actor_id=actor,
        source_kind="killswitch_oauth_revoked" if revocation.ok else "killswitch_oauth_revoke_failed",
        source_ref=row.id,
        summary=f"kill switch: OAuth revocation for {row.provider} — {revocation.outcome}",
        detail={
            "integration_id": str(row.id),
            "provider": row.provider,
            "outcome": revocation.outcome,
            "note": revocation.note,
            "http_status": revocation.http_status,
        },
    )

    await emit_ledger_event(
        session,
        tenant_id=row.tenant_id,
        engagement_id=None,
        occurred_at=now,
        actor_kind="user",
        actor_id=actor,
        source_kind="killswitch_queue_purged" if purge_ok else "killswitch_queue_purge_failed",
        source_ref=row.id,
        summary=f"kill switch: queue purge for {row.provider}",
        detail={"integration_id": str(row.id), "provider": row.provider, **purge_detail},
    )

    # Phase 3 — stored-secret deletion. Pure dict surgery; a failure here
    # would be a code bug, but it still gets its own distinct ledger kind.
    try:
        secrets_detail = _delete_secrets(row)
        secrets_ok = True
    except Exception as exc:
        logger.exception("integration.killswitch_secrets_delete_error")
        secrets_ok = False
        secrets_detail = {"error": repr(exc)}
    await emit_ledger_event(
        session,
        tenant_id=row.tenant_id,
        engagement_id=None,
        occurred_at=now,
        actor_kind="user",
        actor_id=actor,
        source_kind="killswitch_secrets_deleted" if secrets_ok else "killswitch_secrets_delete_failed",
        source_ref=row.id,
        summary=f"kill switch: stored secrets deleted for {row.provider}",
        detail={"integration_id": str(row.id), "provider": row.provider, **secrets_detail},
    )

    row.state = "disabled"
    row.disabled_at = now
    row.updated_at = now
    if actor_id is not None:
        await append_strategist_activity(
            session,
            tenant_id=row.tenant_id,
            actor_id=actor_id,
            category="integration_kill_switch",
            summary=f"Integration kill-switch: {row.provider}",
            detail={"integration_id": str(row.id), "provider": row.provider},
            ref_id=row.id,
        )
    await session.commit()
    await session.refresh(row)

    logger.info(
        "integration.killswitch_triggered",
        extra={
            "event": "integration.killswitch_triggered",
            "tenant_id": str(row.tenant_id),
            "integration_id": str(row.id),
            "provider": row.provider,
            "oauth_revocation": revocation.outcome,
            "queue_purge_ok": purge_ok,
            "secrets_deleted": secrets_ok,
        },
    )
    return {
        "ok": True,
        "already_disabled": False,
        "integration_id": row.id,
        "tenant_id": row.tenant_id,
        "oauth_revocation": {"outcome": revocation.outcome, "note": revocation.note},
        "queue_purge": purge_detail if purge_ok else {"failed": True, **purge_detail},
        "secrets_deleted": secrets_ok,
    }
