"""Tenant-scoped message body storage (Story 3-2) — ``stub`` now, S3 later."""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

from control_plane.config.settings import get_settings

_SAFE_ID = re.compile(r"[^a-zA-Z0-9._-]+")


def _slug_message_id(message_id: str) -> str:
    s = _SAFE_ID.sub("_", message_id.strip())[:200]
    return s or "msg"


def body_ref_for_stub(tenant_id: uuid.UUID, message_id: str) -> str:
    """Opaque ref matching ``body_ref`` in canonical payload (stub prefix)."""
    return f"stub://{tenant_id}/mail/{_slug_message_id(message_id)}.txt"


def _root_dir() -> Path:
    s = get_settings()
    if s.ingest_email_body_stub_dir and str(s.ingest_email_body_stub_dir).strip():
        return Path(s.ingest_email_body_stub_dir).expanduser().resolve()
    import tempfile

    return Path(tempfile.gettempdir()) / "deployai-email-bodies"


async def store_email_body(*, tenant_id: uuid.UUID, message_id: str, content: str) -> str:
    """Write UTF-8 body; return :func:`body_ref_for_stub` (S3 TBD)."""
    s = get_settings()
    if s.ingest_email_body_mode != "stub":
        raise NotImplementedError("ingest_email_body_mode=s3 is not implemented yet (use stub).")
    sl = _slug_message_id(message_id)
    path = _root_dir() / str(tenant_id) / "mail" / f"{sl}.txt"

    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    await asyncio.to_thread(_write)
    return body_ref_for_stub(tenant_id, message_id)
