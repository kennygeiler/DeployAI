"""Send upload ASR / transcribe jobs to SQS (Epic 3 Story 3-4)."""

from __future__ import annotations

import json
import logging
import uuid

import boto3  # type: ignore[import-untyped]

from control_plane.config.settings import get_settings

_LOG = logging.getLogger(__name__)

_JOB_VERSION = 1


def try_send_transcribe_job_sqs(
    *,
    tenant_id: uuid.UUID,
    object_key: str,
    upload_id: uuid.UUID,
    s3_uri: str,
    s3_object_size: int,
    recording_jurisdiction: str,
) -> bool:
    """If ``ingest_upload_sqs_url`` is set, send a JSON job. On failure, logs; returns False (never raises)."""
    s = get_settings()
    u = (s.ingest_upload_sqs_url or "").strip()
    if not u:
        return False
    region = (s.upload_artifact_s3_region or "us-east-1").strip() or "us-east-1"
    body = {
        "v": _JOB_VERSION,
        "tenant_id": str(tenant_id),
        "upload_id": str(upload_id),
        "object_key": object_key,
        "s3_uri": s3_uri,
        "s3_object_size": int(s3_object_size),
        "recording_jurisdiction": (recording_jurisdiction or "").strip(),
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"))
    client = boto3.client("sqs", region_name=region)
    try:
        client.send_message(QueueUrl=u, MessageBody=raw)
    except Exception:
        _LOG.exception(
            "ingest.upload.sqs_send_failed",
            extra={"tenant": str(tenant_id), "upload_id": str(upload_id), "key": object_key},
        )
        return False
    _LOG.info(
        "ingest.upload.sqs_job_sent",
        extra={"tenant": str(tenant_id), "upload_id": str(upload_id), "key": object_key},
    )
    return True
