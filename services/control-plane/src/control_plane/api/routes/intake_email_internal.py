"""Inbound engagement email — webhook + address API (Wave 5 IN1).

Two routers, both mounted under ``/internal/v1``:

- ``POST /intake/email`` — the inbound-email provider webhook (Postmark JSON
  shape). Auth is a dedicated shared secret (``X-DeployAI-Intake-Secret`` vs
  ``DEPLOYAI_INTAKE_WEBHOOK_SECRET``), NOT the internal key: the provider is
  an external caller and must never hold the key that opens every internal
  route. Secret unset → 404 (same "disabled is indistinguishable from absent"
  posture as demo mode). Delivery problems that are the sender's fault
  (unknown/revoked address, oversize, rate limit) answer 200 with
  ``dropped: true`` — never an error status and never a bounce, so a probe
  cannot use the webhook to test which addresses exist.

- ``GET /engagements/{id}/intake-address`` + ``POST .../regenerate`` — the
  BFF-facing address API, gated with ``require_tenant_scoped`` like its
  ``engagements_internal`` siblings. Read mints the address lazily on first
  call; regenerate revokes the active address and mints a replacement.
  Role gating (regenerate = admin-only) lives in the web BFF, which is the
  layer that knows the acting user; these routes trust the internal caller.
"""

from __future__ import annotations

import hmac
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from llm_provider_py.types import LLMProvider
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.agents.llm import get_llm_provider
from control_plane.config.internal_auth import require_tenant_scoped
from control_plane.config.settings import get_settings
from control_plane.db import AppDbSession, TenantDbSession, tenant_request_session, tenant_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.domain.engagement import Engagement
from control_plane.domain.intake_addresses import EngagementIntakeAddress
from control_plane.infra.canonical_idempotent_write import try_insert_with_ingestion_dedup
from control_plane.infra.rate_limit import MemoryTokenBucketLimiter, redis_fixed_window_check
from control_plane.infra.redis_client import get_async_redis
from control_plane.ledger import emit_ledger_event
from control_plane.services.intake_email import (
    MAX_TEXT_BYTES,
    RATE_LIMIT_PER_HOUR,
    content_fingerprint,
    extract_body_text,
    get_or_create_intake_address,
    intake_dedup_key,
    parse_occurred_at,
    recipient_local_parts,
    regenerate_intake_address,
    render_intake_email,
)

_LOG = logging.getLogger(__name__)

INTAKE_SECRET_HEADER = "X-DeployAI-Intake-Secret"

router = APIRouter(prefix="/engagements", tags=["intake-email"])
webhook_router = APIRouter(prefix="/intake", tags=["intake-email"])


# --- Provider webhook --------------------------------------------------------

_RATE_WINDOW_SECONDS = 3600

# Process-local fallback when Redis is not configured — same single-instance
# trade-off as the API rate limiter (see infra/rate_limit.py module docstring).
_memory_limiter = MemoryTokenBucketLimiter()


def reset_intake_rate_limiter_state() -> None:
    """Test helper: clear the in-memory per-address buckets."""
    _memory_limiter.reset()


async def _intake_rate_allowed(local_part: str) -> bool:
    """~60 accepted messages per address per hour. Redis errors fail open."""
    key = f"intake:addr:{local_part}"
    if os.environ.get("DEPLOYAI_REDIS_URL"):
        try:
            decision = await redis_fixed_window_check(
                get_async_redis(),
                key,
                budget=RATE_LIMIT_PER_HOUR,
                window_seconds=_RATE_WINDOW_SECONDS,
            )
            return decision.allowed
        except Exception:
            _LOG.warning("intake_email.rate_limit_redis_unavailable — failing open", exc_info=True)
            return True
    decision = _memory_limiter.check(
        key,
        capacity=float(RATE_LIMIT_PER_HOUR),
        refill_per_second=RATE_LIMIT_PER_HOUR / _RATE_WINDOW_SECONDS,
        now=time.monotonic(),
    )
    return decision.allowed


def _require_intake_secret(provided: str | None) -> None:
    secret = (get_settings().intake_webhook_secret or "").strip()
    if not secret:
        # 404 (not 401/403) so a probe cannot distinguish "feature disabled"
        # from "endpoint absent" — mirrors the demo-session gate.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
    if not provided or not hmac.compare_digest(provided.encode(), secret.encode()):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or missing {INTAKE_SECRET_HEADER}",
        )


def _dropped(reason: str) -> dict[str, Any]:
    return {"dropped": True, "reason": reason}


@webhook_router.post("/email")
async def receive_intake_email(
    request: Request,
    session: AppDbSession,
    llm: Annotated[LLMProvider, Depends(get_llm_provider)],
    x_deployai_intake_secret: Annotated[str | None, Header(alias=INTAKE_SECRET_HEADER)] = None,
) -> dict[str, Any]:
    """Land one provider-delivered email as an ``email.thread`` canonical event.

    Postmark inbound JSON shape, parsed defensively. Attachments are ignored
    (v1). Sender-attributable drops answer 200 — see module docstring.
    """
    _require_intake_secret(x_deployai_intake_secret)

    try:
        payload = await request.json()
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="body must be a JSON object")

    # Resolve OUR intake address among the recipients (there may be several —
    # the deal address is typically CC'd). Unscoped lookup, same posture as
    # the invite token_hash resolve: no tenant scope exists yet.
    local_parts = recipient_local_parts(payload)
    if not local_parts:
        return _dropped("no_recipients")
    r = await session.execute(
        select(EngagementIntakeAddress).where(EngagementIntakeAddress.local_part.in_(local_parts))
    )
    addresses = list(r.scalars().all())
    address = next((a for a in addresses if a.revoked_at is None), None)
    if address is None:
        # Unknown and revoked look identical to the sender (no bounce). The
        # reason string distinguishes them only for the authenticated caller.
        return _dropped("revoked_address" if addresses else "unknown_address")

    text = extract_body_text(payload)
    if not text:
        return _dropped("empty_body")
    if len(text.encode("utf-8")) > MAX_TEXT_BYTES:
        return _dropped("oversize")
    if not await _intake_rate_allowed(address.local_part):
        # 200, not 429: a 429 for a valid address vs 200 for an unknown one
        # would leak validity through status codes. Provider-side redelivery
        # of the dropped message is lost by design (documented v1 limit).
        return _dropped("rate_limited")

    def _field(key: str) -> str:
        v = payload.get(key)
        return v if isinstance(v, str) else ""

    subject = _field("Subject")
    from_addr = _field("From")
    date_raw = _field("Date")
    message_id = _field("MessageID")
    occurred_at = parse_occurred_at(payload)
    tenant_id = address.tenant_id
    engagement_id = address.engagement_id

    dedup = intake_dedup_key(
        engagement_id=engagement_id,
        message_id=message_id,
        fallback_fingerprint=content_fingerprint(subject=subject, sender=from_addr, date=date_raw, text=text),
    )
    event_payload: dict[str, Any] = {
        "subject": subject,
        "from": from_addr,
        "date": date_raw,
        "text": text,
        "message_id": message_id,
        "intake_local_part": address.local_part,
    }
    async with tenant_session(tenant_id) as t_sess:
        inserted = await try_insert_with_ingestion_dedup(
            t_sess,
            tenant_id=tenant_id,
            event_type="email.thread",
            occurred_at=occurred_at,
            source_ref=f"intake:email:{address.local_part}@{dedup[-32:]}",
            payload=event_payload,
            ingestion_dedup_key=dedup,
            engagement_id=engagement_id,
        )
        er = await t_sess.execute(
            select(CanonicalMemoryEvent.id).where(
                CanonicalMemoryEvent.tenant_id == tenant_id,
                CanonicalMemoryEvent.ingestion_dedup_key == dedup,
            )
        )
        event_id = er.scalar_one()
        if inserted:
            await emit_ledger_event(
                t_sess,
                tenant_id=tenant_id,
                engagement_id=engagement_id,
                occurred_at=datetime.now(UTC),
                actor_kind="system",
                actor_id="intake_email",
                source_kind="intake_email_received",
                source_ref=event_id,
                summary=f"intake email received: {subject or '(no subject)'}"[:500],
                detail={"from": from_addr, "message_id": message_id, "subject": subject},
            )
        await t_sess.commit()

    extract_error: str | None = None
    if inserted:
        # Chain Cartographer extraction like the BFF ingest path does —
        # best-effort: the event is real even when the agent hiccups.
        from control_plane.api.routes.engagements_internal import extract_engagement_proposals

        try:
            # Request-session semantics: the extract handler commits mid-flow.
            async with tenant_request_session(tenant_id) as x_sess:
                await extract_engagement_proposals(
                    engagement_id=engagement_id,
                    session=x_sess,
                    tenant_id=tenant_id,
                    event_id=event_id,
                    llm=llm,
                    force=False,
                )
        except Exception as exc:
            extract_error = f"{type(exc).__name__}: {exc}"
            _LOG.warning(
                "intake_email.extract_failed",
                extra={"event_id": str(event_id), "engagement_id": str(engagement_id)},
                exc_info=True,
            )
    return {
        "dropped": False,
        "deduplicated": not inserted,
        "event_id": str(event_id),
        "extract_error": extract_error,
    }


# --- Address read / regenerate (BFF-facing) ----------------------------------


class IntakeAddressRead(BaseModel):
    local_part: str
    email: str | None
    created_at: datetime


class IntakeAddressRegenerate(BaseModel):
    """Optional metadata — the BFF passes the acting admin's id."""

    actor_id: str | None = Field(default=None, max_length=200)


async def _require_engagement(session: AsyncSession, tenant_id: uuid.UUID, engagement_id: uuid.UUID) -> Engagement:
    r = await session.execute(
        select(Engagement).where(Engagement.tenant_id == tenant_id, Engagement.id == engagement_id)
    )
    eng = r.scalar_one_or_none()
    if eng is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement not found")
    return eng


def _address_read(row: EngagementIntakeAddress) -> IntakeAddressRead:
    return IntakeAddressRead(
        local_part=row.local_part,
        email=render_intake_email(row.local_part),
        created_at=row.created_at,
    )


@router.get(
    "/{engagement_id}/intake-address",
    response_model=IntakeAddressRead,
    dependencies=[Depends(require_tenant_scoped)],
)
async def get_intake_address(
    engagement_id: uuid.UUID,
    session: TenantDbSession,
    tenant_id: Annotated[uuid.UUID, Query()],
) -> IntakeAddressRead:
    """The engagement's active intake address, minted lazily on first read."""
    eng = await _require_engagement(session, tenant_id, engagement_id)
    row = await get_or_create_intake_address(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        engagement_name=eng.name,
    )
    await session.commit()
    await session.refresh(row)
    return _address_read(row)


@router.post(
    "/{engagement_id}/intake-address/regenerate",
    response_model=IntakeAddressRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_tenant_scoped)],
)
async def regenerate_intake_address_route(
    engagement_id: uuid.UUID,
    session: TenantDbSession,
    tenant_id: Annotated[uuid.UUID, Query()],
    body: IntakeAddressRegenerate | None = None,
) -> IntakeAddressRead:
    """Revoke the active address and mint a replacement (admin-only in the BFF)."""
    eng = await _require_engagement(session, tenant_id, engagement_id)
    row = await regenerate_intake_address(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        engagement_name=eng.name,
    )
    await emit_ledger_event(
        session,
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        occurred_at=datetime.now(UTC),
        actor_kind="user",
        actor_id=(body.actor_id if body else None),
        source_kind="intake_address_regenerated",
        source_ref=row.id,
        summary="intake address regenerated",
        detail={"engagement_id": str(engagement_id)},
    )
    await session.commit()
    await session.refresh(row)
    return _address_read(row)
