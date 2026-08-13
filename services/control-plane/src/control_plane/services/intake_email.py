"""Inbound engagement email intake (Wave 5 IN1).

Address lifecycle + Postmark-shaped inbound payload handling. The route
(``api/routes/intake_email_internal.py``) owns HTTP concerns; everything
here is session-in, values-out so the pieces are testable without a server.

v1 limits (documented in ``docs/ops/intake-email.md``):
- attachments are ignored;
- ``TextBody`` (or the naive HTML strip of ``HtmlBody``) is capped at 500KB;
- ~60 accepted messages per address per hour (fixed window).
"""

from __future__ import annotations

import hashlib
import re
import secrets
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.settings import get_settings
from control_plane.domain.intake_addresses import EngagementIntakeAddress

MAX_TEXT_BYTES = 500_000
"""Hard cap on the ingested body (bytes of UTF-8). Oversize → dropped:oversize."""

RATE_LIMIT_PER_HOUR = 60
"""Accepted messages per intake address per hour (fixed window)."""

_SLUG_MAX = 30
# Lowercase-only so address matching can be case-insensitive (mail providers
# preserve sender-typed case; we fold recipients to lowercase on lookup), and
# hyphen-free so ``<slug>-<token>`` splits unambiguously. 24 chars of a
# 36-symbol alphabet ≈ 124 bits — comfortably past the ≥16-url-safe-chars bar.
_TOKEN_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"
_TOKEN_LEN = 24


def slug_for_engagement_name(name: str) -> str:
    """Lowercased, hyphenated, ≤30-char slug; ``"engagement"`` when nothing survives."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    s = s[:_SLUG_MAX].rstrip("-")
    return s or "engagement"


def mint_local_part(engagement_name: str) -> str:
    """``<slug>-<token>``: slug for humans, token for unguessability."""
    token = "".join(secrets.choice(_TOKEN_ALPHABET) for _ in range(_TOKEN_LEN))
    return f"{slug_for_engagement_name(engagement_name)}-{token}"


def render_intake_email(local_part: str) -> str | None:
    """Full address when ``DEPLOYAI_INTAKE_EMAIL_DOMAIN`` is set, else ``None``."""
    domain = (get_settings().intake_email_domain or "").strip()
    return f"{local_part}@{domain}" if domain else None


async def get_or_create_intake_address(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    engagement_name: str,
) -> EngagementIntakeAddress:
    """Return the engagement's active address, minting one lazily on first read.

    A concurrent first read can race on the partial unique index; the loser
    rolls back and re-selects the winner's row.
    """
    active = await _active_address(session, engagement_id)
    if active is not None:
        return active
    row = EngagementIntakeAddress(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        local_part=mint_local_part(engagement_name),
    )
    session.add(row)
    try:
        await session.flush()
    except IntegrityError:
        await session.rollback()
        raced = await _active_address(session, engagement_id)
        if raced is None:
            raise
        return raced
    return row


async def _active_address(session: AsyncSession, engagement_id: uuid.UUID) -> EngagementIntakeAddress | None:
    r = await session.execute(
        select(EngagementIntakeAddress).where(
            EngagementIntakeAddress.engagement_id == engagement_id,
            EngagementIntakeAddress.revoked_at.is_(None),
        )
    )
    return r.scalar_one_or_none()


async def regenerate_intake_address(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    engagement_id: uuid.UUID,
    engagement_name: str,
) -> EngagementIntakeAddress:
    """Revoke the active address (if any) and mint a replacement. Caller commits."""
    active = await _active_address(session, engagement_id)
    if active is not None:
        active.revoked_at = datetime.now(UTC)
        await session.flush()
    row = EngagementIntakeAddress(
        tenant_id=tenant_id,
        engagement_id=engagement_id,
        local_part=mint_local_part(engagement_name),
    )
    session.add(row)
    await session.flush()
    return row


# --- Postmark inbound payload parsing ---------------------------------------
#
# Shape reference: https://postmarkapp.com/developer/webhooks/inbound-webhook
# Parsed defensively — every field may be missing or the wrong type; the
# webhook must never 500 on provider-shaped garbage.


_TAG_RE = re.compile(r"<[^>]*>")
_BLOCK_END_RE = re.compile(r"</(?:p|div|br|tr|li|h[1-6])\s*/?>|<br\s*/?>", re.IGNORECASE)
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b.*?</\1\s*>", re.IGNORECASE | re.DOTALL)


def naive_html_to_text(html: str) -> str:
    """Strip tags for the ``HtmlBody``-only fallback. Not a sanitizer — the
    output is stored as inert text, never re-rendered as HTML."""
    s = _SCRIPT_STYLE_RE.sub(" ", html)
    s = _BLOCK_END_RE.sub("\n", s)
    s = _TAG_RE.sub(" ", s)
    s = s.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"')
    return re.sub(r"[ \t]+", " ", s).strip()


def _str(v: object) -> str:
    return v if isinstance(v, str) else ""


def recipient_local_parts(payload: dict[str, Any]) -> list[str]:
    """Local parts of every recipient in ``ToFull``/``CcFull``/``To`` — ours may
    be any of them (the sender may have CC'd the deal address)."""
    out: list[str] = []
    for key in ("ToFull", "CcFull", "BccFull"):
        entries = payload.get(key)
        if isinstance(entries, list):
            for e in entries:
                if isinstance(e, dict):
                    addr = _str(e.get("Email"))
                    if "@" in addr:
                        out.append(addr.split("@", 1)[0].strip().lower())
    for key in ("To", "Cc"):
        raw = _str(payload.get(key))
        for part in raw.split(","):
            addr = part.strip()
            if "<" in addr:  # "Name <a@b>" form
                addr = addr.split("<", 1)[1].split(">", 1)[0]
            if "@" in addr:
                out.append(addr.split("@", 1)[0].strip().lower())
    # de-dup preserving order
    seen: set[str] = set()
    uniq: list[str] = []
    for lp in out:
        if lp and lp not in seen:
            seen.add(lp)
            uniq.append(lp)
    return uniq


def extract_body_text(payload: dict[str, Any]) -> str:
    """``TextBody`` preferred; naive HTML strip of ``HtmlBody`` as fallback."""
    text = _str(payload.get("TextBody")).strip()
    if text:
        return text
    html = _str(payload.get("HtmlBody")).strip()
    return naive_html_to_text(html) if html else ""


def parse_occurred_at(payload: dict[str, Any]) -> datetime:
    """Postmark ``Date`` header (RFC 2822) → aware datetime; ``now`` when unparseable."""
    raw = _str(payload.get("Date")).strip()
    if raw:
        from email.utils import parsedate_to_datetime

        try:
            dt = parsedate_to_datetime(raw)
            return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)
        except (TypeError, ValueError):
            pass
    return datetime.now(UTC)


def intake_dedup_key(*, engagement_id: uuid.UUID, message_id: str, fallback_fingerprint: str) -> str:
    """``intake:email:<engagement>:<message-id>:v1`` — re-delivery safe.

    Providers occasionally omit ``MessageID``; then a content fingerprint
    (subject+from+date+text hash) stands in so a true redelivery still dedups
    while distinct messages do not collide.
    """
    from deployai_ingestlib.idempotency import canonical_ingestion_dedup_key

    mid = message_id.strip() or f"fp-{fallback_fingerprint}"
    return canonical_ingestion_dedup_key(provider="intake", source_id=f"email:{engagement_id}:{mid}", version="v1")


def content_fingerprint(*, subject: str, sender: str, date: str, text: str) -> str:
    digest = hashlib.sha256("\x1f".join((subject, sender, date, text)).encode("utf-8")).hexdigest()
    return digest[:32]
