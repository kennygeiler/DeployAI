"""Stub storage for meeting transcript VTT (Story 3-3) — reuses body stub dir + email_mode gate."""

from __future__ import annotations

import asyncio
import re
import uuid
from pathlib import Path

from control_plane.config.settings import get_settings

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


def _slug(artifact_id: str) -> str:
    s = _SAFE.sub("_", artifact_id.strip())[:200]
    return s or "tr"


def transcript_ref_for_stub(tenant_id: uuid.UUID, artifact_id: str) -> str:
    return f"stub://{tenant_id}/transcripts/{_slug(artifact_id)}.vtt"


def _root_dir() -> Path:
    s = get_settings()
    if s.ingest_email_body_stub_dir and str(s.ingest_email_body_stub_dir).strip():
        return Path(s.ingest_email_body_stub_dir).expanduser().resolve()
    import tempfile

    return Path(tempfile.gettempdir()) / "deployai-email-bodies"


async def store_transcript_vtt(*, tenant_id: uuid.UUID, artifact_id: str, content: str) -> str:
    """Write UTF-8 VTT; returns :func:`transcript_ref_for_stub` (S3 TBD)."""
    s = get_settings()
    if s.ingest_email_body_mode != "stub":
        raise NotImplementedError("transcript store requires ingest_email_body_mode=stub (S3 TBD).")
    sl = _slug(artifact_id)
    path = _root_dir() / str(tenant_id) / "transcripts" / f"{sl}.vtt"

    def _write() -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    await asyncio.to_thread(_write)
    return transcript_ref_for_stub(tenant_id, artifact_id)
