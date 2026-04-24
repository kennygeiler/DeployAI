"""S3 presigned POST for direct client → bucket uploads (Epic 3 Story 3-4, FR12, AR11)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]

from control_plane.config.settings import get_settings
from control_plane.exceptions import UploadPresignNotConfiguredError

_MAX_BYTES = 500 * 1024 * 1024
_EXT_OK = frozenset({".mp3", ".m4a", ".mp4", ".wav"})

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")


@dataclass(frozen=True, slots=True)
class PresignResult:
    """Browser/client posts multipart form to ``url`` with ``form_fields`` + file last."""

    url: str
    form_fields: dict[str, str]
    object_key: str
    upload_id: str
    expires_in: int = 3600


def _safe_filename(name: str) -> str:
    s = _SAFE.sub("_", name.rsplit("/")[-1].strip())[:200]
    return s or "upload.bin"


def _validate_artifact_guards(*, filename: str, content_type: str, file_size: int) -> None:
    if not (0 < file_size <= _MAX_BYTES):
        raise ValueError("file_size must be between 1 and 500 MB")
    base = str(filename or "").rsplit("/")[-1]
    if "." not in base:
        raise ValueError("filename must have an extension")
    suf = f".{base.rsplit('.', 1)[-1].lower()}"
    if suf not in _EXT_OK:
        raise ValueError("allowed extensions: .mp3 .m4a .mp4 .wav")
    ct = content_type.strip().lower()
    if not (ct.startswith("audio/") or ct.startswith("video/")) and ct != "application/octet-stream":
        raise ValueError("content_type must be audio/* or video/* (or application/octet-stream)")


def presign_meeting_artifact(
    *,
    tenant_id: uuid.UUID,
    filename: str,
    content_type: str,
    file_size: int,
) -> PresignResult:
    _validate_artifact_guards(filename=filename, content_type=content_type, file_size=file_size)
    s = get_settings()
    bucket = (s.upload_artifact_s3_bucket or "").strip()
    if not bucket:
        raise UploadPresignNotConfiguredError
    reg = (s.upload_artifact_s3_region or "us-east-1").strip() or "us-east-1"
    raw_pre = (s.upload_artifact_s3_key_prefix or "ingest/artifacts").strip().strip("/")
    uid = uuid.uuid4()
    fn = _safe_filename(filename)
    key = f"{raw_pre}/tenant/{tenant_id}/uploads/{uid}/{fn}"
    s3: Any = boto3.client("s3", region_name=reg, config=Config(signature_version="s3v4"))
    out: dict[str, Any] = s3.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields={"Content-Type": content_type},
        Conditions=[
            ["content-length-range", 1, _MAX_BYTES],
            ["eq", "$Content-Type", content_type],
        ],
        ExpiresIn=3600,
    )
    form_raw = out.get("fields") or {}
    form_fields: dict[str, str] = {
        k: (v.decode("utf-8") if isinstance(v, bytes) else str(v)) for k, v in form_raw.items()
    }
    return PresignResult(
        url=str(out["url"]),
        form_fields=form_fields,
        object_key=key,
        upload_id=str(uid),
    )
