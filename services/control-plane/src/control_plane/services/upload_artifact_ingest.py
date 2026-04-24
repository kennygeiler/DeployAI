"""Finalize S3 meeting upload → canonical `upload.transcript` (Epic 3 Story 3-4)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from control_plane.config.settings import get_settings
from control_plane.db import tenant_session
from control_plane.domain.canonical_memory.events import CanonicalMemoryEvent
from control_plane.infra.transcript_artifact_store import store_transcript_plain_text
from control_plane.services.upload_artifact_s3 import (
    assert_artifact_key_for_upload,
    head_upload_artifact_size,
)

_LOG = logging.getLogger(__name__)

_STUB_TRANSCRIPTION = (
    "Transcription pending (dev stub). Audio reference is recorded in the payload; "
    "configure a worker + provider (Story 3-4) for ASR output."
)


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


def _emit_ingest_job_stub(
    *, tenant_id: uuid.UUID, object_key: str, content_length: int, transcript_ref: str
) -> None:
    _LOG.info(
        "ingest.upload.registered",
        extra={
            "tenant": str(tenant_id),
            "key": object_key,
            "bytes": content_length,
            "transcript_ref": transcript_ref,
        },
    )


async def complete_meeting_artifact(
    *,
    tenant_id: uuid.UUID,
    object_key: str,
    upload_id: uuid.UUID,
    consent_two_party: bool,
    recording_jurisdiction: str,
) -> dict[str, Any]:
    if not consent_two_party:
        raise ValueError("two-party consent is required (NFR39) before finalizing an upload")
    j = recording_jurisdiction.strip()
    if len(j) < 2 or len(j) > 128:
        raise ValueError("recording_jurisdiction must be 2-128 characters (NFR39 metadata)")

    assert_artifact_key_for_upload(
        object_key=object_key, tenant_id=tenant_id, upload_id=upload_id
    )
    size = await asyncio.to_thread(head_upload_artifact_size, object_key=object_key)
    s = get_settings()
    b = (s.upload_artifact_s3_bucket or "").strip()
    s3_uri = f"s3://{b}/{object_key}" if b else f"s3://<bucket>/{object_key}"

    source_ref = f"upload:artifact:{upload_id}"
    async with tenant_session(tenant_id) as t0:
        if await _source_ref_exists(t0, tenant_id=tenant_id, source_ref=source_ref):
            return {"inserted": 0, "idempotent": True, "source_ref": source_ref}

    tref = await store_transcript_plain_text(
        tenant_id=tenant_id,
        artifact_id=f"upload-{upload_id}",
        text=_STUB_TRANSCRIPTION,
    )
    _emit_ingest_job_stub(
        tenant_id=tenant_id,
        object_key=object_key,
        content_length=size,
        transcript_ref=tref,
    )
    payload: dict[str, Any] = {
        "session_unit": "upload.transcript",
        "s3_uri": s3_uri,
        "s3_object_key": object_key,
        "s3_object_size": size,
        "upload_id": str(upload_id),
        "transcript_ref": tref,
        "transcription_status": "stub",
        "consent_two_party": True,
        "recording_jurisdiction": j,
    }
    now = datetime.now(UTC)
    async with tenant_session(tenant_id) as t_sess:
        t_sess.add(
            CanonicalMemoryEvent(
                tenant_id=tenant_id,
                event_type="upload.transcript",
                occurred_at=now,
                source_ref=source_ref,
                payload=payload,
            )
        )
        try:
            await t_sess.commit()
        except IntegrityError:
            await t_sess.rollback()
            if await _source_ref_exists(t_sess, tenant_id=tenant_id, source_ref=source_ref):
                return {"inserted": 0, "idempotent": True, "source_ref": source_ref}
            raise
    return {"inserted": 1, "idempotent": False, "source_ref": source_ref}
