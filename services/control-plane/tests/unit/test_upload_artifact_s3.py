"""S3 presign + upload routes (Story 3-4)."""

from __future__ import annotations

import uuid
from pathlib import Path

import boto3
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from moto import mock_aws

from control_plane.auth.jwt_tokens import clear_jwt_key_cache, create_access_token
from control_plane.config.settings import clear_settings_cache, get_settings
from control_plane.main import app
from control_plane.services.upload_artifact_s3 import presign_meeting_artifact

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
