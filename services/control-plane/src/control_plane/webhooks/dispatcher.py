"""Per-tenant webhook dispatcher — HMAC-signed POST with one retry, best-effort."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import UTC, datetime
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.db import _get_app_session_maker
from control_plane.domain.webhooks.models import TenantWebhook, WebhookDelivery

WEBHOOK_EVENTS: tuple[str, ...] = ("insight.created", "proposal.added", "extraction.completed")

_REQUEST_TIMEOUT_SECONDS = 10.0
_RETRY_DELAY_SECONDS = 30.0

# Strong references to in-flight delivery tasks so the event loop's garbage
# collector cannot drop them mid-POST (asyncio only holds weak refs).
_background_tasks: set[asyncio.Task[None]] = set()


def sign_payload(secret: str, body: bytes) -> str:
    """Return the ``X-DeployAI-Signature`` header value for ``body``."""
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _json_default(value: Any) -> str:
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _serialize(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, default=_json_default, separators=(",", ":")).encode("utf-8")


async def _post_once(url: str, body: bytes, signature: str) -> tuple[int | None, str | None]:
    headers = {
        "Content-Type": "application/json",
        "X-DeployAI-Signature": signature,
    }
    try:
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS) as client:
            resp = await client.post(url, content=body, headers=headers)
    except httpx.HTTPError as exc:
        return None, str(exc)[:500]
    if resp.status_code >= 200 and resp.status_code < 300:
        return resp.status_code, None
    return resp.status_code, f"HTTP {resp.status_code}: {resp.text[:200]}"


async def _deliver(
    delivery_id: uuid.UUID,
    url: str,
    body: bytes,
    signature: str,
) -> None:
    status_code, err = await _post_once(url, body, signature)
    attempts = 1
    if err is not None:
        await asyncio.sleep(_RETRY_DELAY_SECONDS)
        status_code, err = await _post_once(url, body, signature)
        attempts = 2

    now = datetime.now(UTC)
    async with _get_app_session_maker()() as session:
        row = await session.get(WebhookDelivery, delivery_id)
        if row is None:
            return
        row.attempts = attempts
        row.response_status = status_code
        row.error = err
        row.status = "succeeded" if err is None else "failed"
        row.completed_at = now
        await session.commit()


async def dispatch(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    event_name: str,
    payload: dict[str, Any],
) -> None:
    """Fire ``event_name`` to every active webhook for ``tenant_id`` subscribed to it.

    Records a delivery row per webhook (status=pending) and schedules the
    HTTP POST in a background task. Returns once delivery rows are
    committed; HTTP work continues in the background and is best-effort.
    """
    if event_name not in WEBHOOK_EVENTS:
        return
    r = await session.execute(
        select(TenantWebhook).where(
            TenantWebhook.tenant_id == tenant_id,
            TenantWebhook.active.is_(True),
        )
    )
    webhooks = [w for w in r.scalars().all() if event_name in (w.events or [])]
    if not webhooks:
        return

    body_dict = {
        "event": event_name,
        "tenant_id": str(tenant_id),
        "data": payload,
    }
    body = _serialize(body_dict)

    deliveries: list[tuple[uuid.UUID, str, bytes, str]] = []
    for w in webhooks:
        delivery = WebhookDelivery(
            webhook_id=w.id,
            event_name=event_name,
            payload=body_dict,
            status="pending",
            attempts=0,
        )
        session.add(delivery)
        await session.flush()
        secret = w.secret_ciphertext or ""
        signature = sign_payload(secret, body)
        deliveries.append((delivery.id, w.url, body, signature))
    await session.commit()

    for delivery_id, url, b, sig in deliveries:
        task = asyncio.create_task(_deliver(delivery_id, url, b, sig))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)
