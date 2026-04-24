"""Consume ``ingest_upload_sqs_url`` jobs and append ``asr.transcript`` (Epic 3 Story 3-4)."""

from __future__ import annotations

import asyncio
import json
import logging
import signal
import sys
import time
import uuid
from datetime import UTC, datetime
from typing import Any, Final

import boto3  # type: ignore[import-untyped]
from ingest.idempotency import canonical_ingestion_dedup_key

from control_plane.config.settings import get_settings
from control_plane.db import tenant_session
from control_plane.infra.canonical_idempotent_write import try_insert_with_ingestion_dedup
from control_plane.infra.transcript_artifact_store import store_transcript_plain_text

_LOG = logging.getLogger(__name__)

_EXPECTED_V: Final[int] = 1
_POLL_WAIT: Final[int] = 20


def _asr_plain_text(*, upload_id: uuid.UUID, object_key: str, s3_object_size: int, recording_jurisdiction: str) -> str:
    mode = (get_settings().upload_asr_mode or "stub").strip()
    if mode == "transcribe":
        _LOG.info(
            "ingest.upload.asr_transcribe_mode_stub_only",
            extra={"upload_id": str(upload_id), "key": object_key},
        )
    return (
        f"[asr] upload_id={upload_id} key={object_key} bytes={s3_object_size} "
        f"jurisdiction={recording_jurisdiction!r} (mode={mode!r}; configure AWS Transcribe for real ASR.)"
    )


def _parse_job(body: str) -> dict[str, Any]:
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError("job body must be a JSON object")
    if int(data.get("v", 0)) != _EXPECTED_V:
        raise ValueError(f"unsupported job version (expected v={_EXPECTED_V})")
    tenant_id = uuid.UUID(str(data["tenant_id"]))
    upload_id = uuid.UUID(str(data["upload_id"]))
    object_key = str(data["object_key"])
    s3_uri = str(data["s3_uri"])
    s3_object_size = int(data["s3_object_size"])
    j = str(data.get("recording_jurisdiction") or "").strip()
    return {
        "tenant_id": tenant_id,
        "upload_id": upload_id,
        "object_key": object_key,
        "s3_uri": s3_uri,
        "s3_object_size": s3_object_size,
        "recording_jurisdiction": j,
    }


async def process_transcribe_job(*, job_body: str) -> str:
    """Idempotently create ``asr.transcript`` from a queue message body. Returns ``inserted`` or ``deduped``."""
    p = _parse_job(job_body)
    tid = p["tenant_id"]
    upload_id: uuid.UUID = p["upload_id"]
    text = _asr_plain_text(
        upload_id=upload_id,
        object_key=p["object_key"],
        s3_object_size=p["s3_object_size"],
        recording_jurisdiction=p["recording_jurisdiction"],
    )
    tref = await store_transcript_plain_text(
        tenant_id=tid,
        artifact_id=f"asr-upload-{upload_id}",
        text=text,
    )
    now = datetime.now(UTC)
    source_ref = f"upload:asr:{upload_id}"
    dedup = canonical_ingestion_dedup_key(provider="upload", source_id=f"asr_transcript:{upload_id}", version="v1")
    rel = f"upload:artifact:{upload_id}"
    payload: dict[str, Any] = {
        "session_unit": "asr.transcript",
        "s3_uri": p["s3_uri"],
        "s3_object_key": p["object_key"],
        "s3_object_size": p["s3_object_size"],
        "upload_id": str(upload_id),
        "transcript_ref": tref,
        "transcription_status": "asr_complete",
        "asr_mode": (get_settings().upload_asr_mode or "stub"),
        "consent_two_party": True,
        "recording_jurisdiction": p["recording_jurisdiction"],
        "related_source_ref": rel,
    }
    async with tenant_session(tid) as t_sess:
        ok = await try_insert_with_ingestion_dedup(
            t_sess,
            tenant_id=tid,
            event_type="asr.transcript",
            occurred_at=now,
            source_ref=source_ref,
            payload=payload,
            ingestion_dedup_key=dedup,
        )
        await t_sess.commit()
    return "inserted" if ok else "deduped"


def _sqs_client() -> Any:
    s = get_settings()
    r = (s.upload_artifact_s3_region or "us-east-1").strip() or "us-east-1"
    return boto3.client("sqs", region_name=r)


async def _handle_one_sqs_message(*, client: Any, queue_url: str, msg: dict[str, Any]) -> None:
    body = str(msg.get("Body") or "")
    rh = str(msg.get("ReceiptHandle") or "")
    if not body or not rh:
        return
    try:
        out = await process_transcribe_job(job_body=body)
    except Exception:
        _LOG.exception("ingest.upload.worker_job_failed", extra={"body_excerpt": body[:200]})
        return
    try:
        client.delete_message(QueueUrl=queue_url, ReceiptHandle=rh)
    except Exception:
        _LOG.exception("ingest.upload.worker_delete_failed", extra={"out": out})


def run_worker_polling() -> None:
    """Block forever: long-poll SQS, process, delete. SIGINT/SIGTERM exit gracefully."""
    s = get_settings()
    u = (s.ingest_upload_sqs_url or "").strip()
    if not u:
        _LOG.error("ingest.upload.worker_no_queue; set DEPLOYAI_INGEST_UPLOAD_SQS_URL")
        sys.exit(2)
    client = _sqs_client()
    stop = False

    def _stop(*_: Any) -> None:
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)
    _LOG.info("ingest.upload.worker_start", extra={"queue": u[:80]})
    while not stop:
        try:
            resp = client.receive_message(
                QueueUrl=u,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=_POLL_WAIT,
                VisibilityTimeout=300,
            )
        except Exception:
            _LOG.exception("ingest.upload.worker_receive_failed")
            time.sleep(2)
            continue
        for m in resp.get("Messages") or []:
            if stop:
                break
            asyncio.run(_handle_one_sqs_message(client=client, queue_url=u, msg=m))
    _LOG.info("ingest.upload.worker_stop")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run_worker_polling()


if __name__ == "__main__":
    main()
