"""S3 presigned POST for direct client → bucket uploads (Epic 3 Story 3-4, FR12, AR11)."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any

import boto3  # type: ignore[import-untyped]
from botocore.config import Config  # type: ignore[import-untyped]
from botocore.exceptions import ClientError  # type: ignore[import-untyped]

from control_plane.config.settings import get_settings
from control_plane.exceptions import UploadPresignNotConfiguredError

_MAX_BYTES = 500 * 1024 * 1024
_EXT_OK = frozenset({".mp3", ".m4a", ".mp4", ".wav"})

_SAFE = re.compile(r"[^a-zA-Z0-9._-]+")
# Matches :func:`_safe_filename` output segment (and presigned object key tail).
_MAX_FILENAME_SEG = 200
_MAX_OBJECT_KEY_LEN = 1024
_FILENAME_SEG_OK = re.compile(rf"^[a-zA-Z0-9._-]{{1,{_MAX_FILENAME_SEG}}}$")


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


def _content_length_upper_bound(*, file_size: int) -> int:
    """S3 policy upper bound for declared size (stops a larger blob than presigned for)."""
    if not (0 < file_size <= _MAX_BYTES):
        raise ValueError("file_size must be between 1 and 500 MB")
    return file_size


def _validate_artifact_guards(*, filename: str, content_type: str, file_size: int) -> None:
    _content_length_upper_bound(file_size=file_size)
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
            ["content-length-range", 1, file_size],
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


def _s3_client(*, region: str) -> Any:
    return boto3.client("s3", region_name=region, config=Config(signature_version="s3v4"))


def assert_artifact_key_for_upload(
    *,
    object_key: str,
    tenant_id: uuid.UUID,
    upload_id: uuid.UUID,
) -> None:
    """Ensure ``object_key`` matches the layout produced by :func:`presign_meeting_artifact`."""
    if len(object_key) > _MAX_OBJECT_KEY_LEN or not object_key:
        raise ValueError("object_key length is invalid")
    if object_key != object_key.strip() or any(c in object_key for c in "\n\r\0"):
        raise ValueError("object_key must be a single line without leading or trailing spaces")
    s = get_settings()
    raw_pre = (s.upload_artifact_s3_key_prefix or "ingest/artifacts").strip().strip("/")
    prefix = f"{raw_pre}/tenant/{tenant_id}/uploads/{upload_id}/"
    if ".." in object_key or not object_key.startswith(prefix):
        raise ValueError("object_key does not match this tenant and upload_id")
    rest = object_key[len(prefix) :]
    if not rest or "/" in rest or "\\" in rest:
        raise ValueError("object_key must end with a single path segment (filename)")
    if "." not in rest:
        raise ValueError("object_key filename must have an allowed extension")
    suf = f".{rest.rsplit('.', 1)[-1].lower()}"
    if suf not in _EXT_OK:
        raise ValueError("object_key must use an allowed file extension (same as presign)")
    if not _FILENAME_SEG_OK.fullmatch(rest):
        raise ValueError("object_key filename must contain only safe characters (same as presign)")


def head_upload_artifact_size(*, object_key: str) -> int:
    """Return S3 object size (bytes) or raise ``FileNotFoundError`` if missing."""
    s = get_settings()
    bucket = (s.upload_artifact_s3_bucket or "").strip()
    if not bucket:
        raise UploadPresignNotConfiguredError
    reg = (s.upload_artifact_s3_region or "us-east-1").strip() or "us-east-1"
    c = _s3_client(region=reg)
    try:
        o: dict[str, Any] = c.head_object(Bucket=bucket, Key=object_key)
    except ClientError as e:
        err: dict[str, Any] = e.response or {}
        code = str((err.get("Error") or {}).get("Code") or "")
        http = int((err.get("ResponseMetadata") or {}).get("HTTPStatusCode", 0) or 0)
        if code in ("404", "NoSuchKey", "NotFound", "Not Found", "NoSuchBucket") or http == 404:
            raise FileNotFoundError("uploaded object not found in S3 (finish POST first)") from e
        if code in ("AccessDenied", "AllAccessDisabled") or http in (401, 403):
            raise PermissionError(
                "S3 access denied for upload finalization; check bucket policy and credentials."
            ) from e
        raise
    cl = o.get("ContentLength")
    if not isinstance(cl, int):
        return int(cl or 0)
    return cl
