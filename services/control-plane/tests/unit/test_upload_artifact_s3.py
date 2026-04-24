"""S3 presign + upload routes (Story 3-4)."""

from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import boto3
import pytest
from botocore.exceptions import ClientError
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from moto import mock_aws

from control_plane.auth.jwt_tokens import clear_jwt_key_cache, create_access_token
from control_plane.config.settings import clear_settings_cache, get_settings
from control_plane.main import app
from control_plane.services.upload_artifact_s3 import (
    assert_artifact_key_for_upload,
    head_upload_artifact_size,
    presign_meeting_artifact,
)

_BUCKET = "deployai-test-upload-1"
_REGION = "us-east-1"


def _write_rsa(tmp: Path) -> tuple[Path, Path]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv_b = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_b = key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv = tmp / "up-priv.pem"
    pub = tmp / "up-pub.pem"
    priv.write_bytes(priv_b)
    pub.write_bytes(pub_b)
    return priv, pub


@mock_aws
def test_presign_meeting_artifact_happy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_BUCKET", _BUCKET)
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_REGION", _REGION)
    get_settings.cache_clear()
    c = boto3.client("s3", region_name=_REGION)
    c.create_bucket(Bucket=_BUCKET)
    tid = uuid.uuid4()
    r = presign_meeting_artifact(
        tenant_id=tid,
        filename="a.m4a",
        content_type="audio/mp4",
        file_size=1000,
    )
    assert _BUCKET in r.url or "amazonaws" in r.url
    assert "key" in r.form_fields
    assert str(tid) in r.object_key
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_presign_api_with_jwt_and_moto(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_BUCKET", _BUCKET)
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_REGION", _REGION)
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    clear_settings_cache()
    clear_jwt_key_cache()
    tid = uuid.uuid4()
    with mock_aws():
        c = boto3.client("s3", region_name=_REGION)
        c.create_bucket(Bucket=_BUCKET)
        tok = create_access_token(
            sub="s1", tid=str(tid), roles=["deployment_strategist"], access_jti="up-1"
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
            res = await cl.post(
                "/upload/artifacts/presign",
                json={
                    "tenant_id": str(tid),
                    "filename": "x.m4a",
                    "content_type": "audio/mp4",
                    "file_size": 1200,
                },
                headers={"Authorization": f"Bearer {tok}"},
            )
    assert res.status_code == 200, res.text
    b = res.json()
    assert b.get("object_key", "").startswith("ingest/artifacts/tenant")
    assert b.get("upload_id")
    clear_jwt_key_cache()
    clear_settings_cache()


@pytest.mark.asyncio
async def test_presign_503_without_bucket(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("DEPLOYAI_UPLOAD_ARTIFACT_S3_BUCKET", "DEPLOYAI_UPLOAD_ARTIFACT_S3_REGION"):
        monkeypatch.delenv(k, raising=False)
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    clear_settings_cache()
    clear_jwt_key_cache()
    tid = uuid.uuid4()
    try:
        tok = create_access_token(
            sub="s1", tid=str(tid), roles=["deployment_strategist"], access_jti="up-2"
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
            res = await cl.post(
                "/upload/artifacts/presign",
                json={
                    "tenant_id": str(tid),
                    "filename": "x.m4a",
                    "content_type": "audio/mp4",
                    "file_size": 1200,
                },
                headers={"Authorization": f"Bearer {tok}"},
            )
        assert res.status_code == 503
    finally:
        clear_jwt_key_cache()
        clear_settings_cache()


def test_content_length_bound_validation() -> None:
    from control_plane.services.upload_artifact_s3 import _content_length_upper_bound

    assert _content_length_upper_bound(file_size=500 * 1024) == 500 * 1024
    with pytest.raises(ValueError, match="500 MB"):
        _content_length_upper_bound(file_size=600 * 1024 * 1024)


@pytest.mark.asyncio
async def test_complete_400_missing_consent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    clear_settings_cache()
    clear_jwt_key_cache()
    tid = uuid.uuid4()
    try:
        tok = create_access_token(
            sub="s1", tid=str(tid), roles=["deployment_strategist"], access_jti="up-c"
        )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cl:
            res = await cl.post(
                "/upload/artifacts/complete",
                json={
                    "tenant_id": str(tid),
                    "object_key": "12345678",
                    "upload_id": str(uuid.uuid4()),
                    "consent_two_party": False,
                    "recording_jurisdiction": "US",
                },
                headers={"Authorization": f"Bearer {tok}"},
            )
        assert res.status_code == 400
        assert "consent" in (res.json().get("detail") or "").lower()
    finally:
        clear_jwt_key_cache()
        clear_settings_cache()


def test_assert_artifact_key_accepts_layout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_REGION", _REGION)
    clear_settings_cache()
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    k = f"ingest/artifacts/tenant/{tid}/uploads/{uid}/clip.m4a"
    try:
        assert_artifact_key_for_upload(object_key=k, tenant_id=tid, upload_id=uid)
    finally:
        clear_settings_cache()


def test_assert_artifact_key_rejects_mismatch() -> None:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    k = f"ingest/artifacts/tenant/{uuid.uuid4()}/uploads/{uid}/a.m4a"
    with pytest.raises(ValueError, match="object_key does not match"):
        assert_artifact_key_for_upload(object_key=k, tenant_id=tid, upload_id=uid)


def test_assert_artifact_key_rejects_bad_extension() -> None:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    k = f"ingest/artifacts/tenant/{tid}/uploads/{uid}/a.exe"
    with pytest.raises(ValueError, match="allowed file extension"):
        assert_artifact_key_for_upload(object_key=k, tenant_id=tid, upload_id=uid)


def test_assert_artifact_key_rejects_path_segment() -> None:
    tid = uuid.uuid4()
    uid = uuid.uuid4()
    k = f"ingest/artifacts/tenant/{tid}/uploads/{uid}/sub/a.m4a"
    with pytest.raises(ValueError, match="single path segment"):
        assert_artifact_key_for_upload(object_key=k, tenant_id=tid, upload_id=uid)


@mock_aws
def test_head_missing_object_file_not_found(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_BUCKET", _BUCKET)
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_REGION", _REGION)
    clear_settings_cache()
    c = boto3.client("s3", region_name=_REGION)
    c.create_bucket(Bucket=_BUCKET)
    some_key = "ingest/artifacts/tenant/x/y/uploads/00000000-0000-0000-0000-000000000001/m.m4a"
    try:
        with pytest.raises(FileNotFoundError, match="not found in S3"):
            head_upload_artifact_size(object_key=some_key)
    finally:
        clear_settings_cache()


def test_head_s3_access_denied_permission_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_BUCKET", _BUCKET)
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_REGION", _REGION)
    clear_settings_cache()
    fake = MagicMock()
    fake.head_object.side_effect = ClientError(
        {
            "Error": {"Code": "AccessDenied", "Message": "Access Denied"},
            "ResponseMetadata": {"HTTPStatusCode": 403},
        },
        "HeadObject",
    )
    k = f"ingest/artifacts/tenant/{uuid.uuid4()}/uploads/{uuid.uuid4()}/a.m4a"
    try:
        with patch("control_plane.services.upload_artifact_s3._s3_client", return_value=fake):
            with pytest.raises(PermissionError, match="S3 access denied"):
                head_upload_artifact_size(object_key=k)
    finally:
        clear_settings_cache()


def test_head_404_by_http_status(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_BUCKET", _BUCKET)
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_REGION", _REGION)
    clear_settings_cache()
    fake = MagicMock()
    fake.head_object.side_effect = ClientError(
        {
            "Error": {"Code": "", "Message": ""},
            "ResponseMetadata": {"HTTPStatusCode": 404},
        },
        "HeadObject",
    )
    k = f"ingest/artifacts/tenant/{uuid.uuid4()}/uploads/{uuid.uuid4()}/a.m4a"
    try:
        with patch("control_plane.services.upload_artifact_s3._s3_client", return_value=fake):
            with pytest.raises(FileNotFoundError, match="not found in S3"):
                head_upload_artifact_size(object_key=k)
    finally:
        clear_settings_cache()
