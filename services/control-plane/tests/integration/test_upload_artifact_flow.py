"""Story 3-4: presign → S3 put (moto) → complete → upload.transcript row."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import boto3
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient
from moto import mock_aws
from sqlalchemy import text
from sqlalchemy.engine import Engine

from control_plane.auth.jwt_tokens import clear_jwt_key_cache, create_access_token
from control_plane.config.settings import clear_settings_cache
from control_plane.db import clear_engine_cache
from control_plane.main import app
from control_plane.workers.transcribe_upload import process_transcribe_job

from .test_account_provision_flow import _async_database_url_from_engine

pytestmark = pytest.mark.integration

_BUCKET = "upload-int-1"
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
    priv = tmp / "up-int-priv.pem"
    pub = tmp / "up-int-pub.pem"
    priv.write_bytes(priv_b)
    pub.write_bytes(pub_b)
    return priv, pub


@pytest_asyncio.fixture
async def upload_http_client(
    postgres_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    priv, pub = _write_rsa(tmp_path)
    monkeypatch.setenv("DATABASE_URL", _async_database_url_from_engine(postgres_engine))
    monkeypatch.setenv("DEPLOYAI_JWT_PRIVATE_KEY_PATH", str(priv))
    monkeypatch.setenv("DEPLOYAI_JWT_PUBLIC_KEY_PATHS", str(pub))
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_BUCKET", _BUCKET)
    monkeypatch.setenv("DEPLOYAI_UPLOAD_ARTIFACT_S3_REGION", _REGION)
    clear_settings_cache()
    clear_jwt_key_cache()
    clear_engine_cache()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, priv
    finally:
        clear_jwt_key_cache()
        clear_settings_cache()
        clear_engine_cache()


def _ins_tenant(conn: Engine, tid: uuid.UUID) -> None:
    with conn.begin() as c:
        c.execute(
            text("INSERT INTO app_tenants (id, name) VALUES (:t, 'upload test')"),
            {"t": str(tid)},
        )


@pytest.mark.asyncio
async def test_upload_presign_put_complete_canonical(
    upload_http_client: tuple[AsyncClient, Any], postgres_engine: Engine
) -> None:
    client, _priv = upload_http_client
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    tok = create_access_token(
        sub="st", tid=str(tid), roles=["deployment_strategist"], access_jti="up-i1"
    )
    with mock_aws():
        s3 = boto3.client("s3", region_name=_REGION)
        s3.create_bucket(Bucket=_BUCKET)
        r0 = await client.post(
            "/upload/artifacts/presign",
            json={
                "tenant_id": str(tid),
                "filename": "clip.m4a",
                "content_type": "audio/mp4",
                "file_size": 2000,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r0.status_code == 200, r0.text
        b0 = r0.json()
        key = b0["object_key"]
        upload_id = b0["upload_id"]
        s3.put_object(Bucket=_BUCKET, Key=key, Body=b"y" * 500, ContentType="audio/mp4")
        r1 = await client.post(
            "/upload/artifacts/complete",
            json={
                "tenant_id": str(tid),
                "object_key": key,
                "upload_id": upload_id,
                "consent_two_party": True,
                "recording_jurisdiction": "US-CA",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        r2 = await client.post(
            "/upload/artifacts/complete",
            json={
                "tenant_id": str(tid),
                "object_key": key,
                "upload_id": upload_id,
                "consent_two_party": True,
                "recording_jurisdiction": "US-CA",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
    assert r1.status_code == 200, r1.text
    assert r1.json().get("inserted") == 1
    assert r2.json().get("inserted") == 0
    assert r2.json().get("idempotent") is True
    src = f"upload:artifact:{upload_id}"
    with postgres_engine.begin() as cx:
        n = cx.execute(
            text(
                "SELECT count(*)::int FROM canonical_memory_events "
                "WHERE tenant_id = CAST(:t AS uuid) AND event_type = 'upload.transcript' "
                "AND source_ref = :s"
            ),
            {"t": str(tid), "s": src},
        ).scalar_one()
    assert int(n) == 1


@pytest.mark.asyncio
async def test_upload_sqs_message_worker_inserts_asr_transcript(
    upload_http_client: tuple[AsyncClient, Any], postgres_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, _priv = upload_http_client
    tid = uuid.uuid4()
    _ins_tenant(postgres_engine, tid)
    tok = create_access_token(
        sub="st2", tid=str(tid), roles=["deployment_strategist"], access_jti="up-i2"
    )
    with mock_aws():
        s3 = boto3.client("s3", region_name=_REGION)
        sqs = boto3.client("sqs", region_name=_REGION)
        s3.create_bucket(Bucket=_BUCKET)
        qurl = sqs.create_queue(QueueName="up-transcribe-jobs")["QueueUrl"]
        monkeypatch.setenv("DEPLOYAI_INGEST_UPLOAD_SQS_URL", qurl)
        clear_settings_cache()
        r0 = await client.post(
            "/upload/artifacts/presign",
            json={
                "tenant_id": str(tid),
                "filename": "long.m4a",
                "content_type": "audio/mp4",
                "file_size": 4000,
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r0.status_code == 200, r0.text
        b0 = r0.json()
        key = b0["object_key"]
        upload_id = b0["upload_id"]
        s3.put_object(Bucket=_BUCKET, Key=key, Body=b"x" * 2000, ContentType="audio/mp4")
        r1 = await client.post(
            "/upload/artifacts/complete",
            json={
                "tenant_id": str(tid),
                "object_key": key,
                "upload_id": upload_id,
                "consent_two_party": True,
                "recording_jurisdiction": "US-CA",
            },
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert r1.status_code == 200, r1.text
        assert r1.json().get("queue_dispatched") is True
        recv = sqs.receive_message(QueueUrl=qurl, MaxNumberOfMessages=1, WaitTimeSeconds=1)
        raw = (recv.get("Messages") or [{}])[0].get("Body")
        assert raw and "upload_id" in raw
        out1 = await process_transcribe_job(job_body=raw)
        out2 = await process_transcribe_job(job_body=raw)
    assert out1 == "inserted"
    assert out2 == "deduped"
    with postgres_engine.begin() as cx:
        n_ingest = cx.execute(
            text(
                "SELECT count(*)::int FROM canonical_memory_events "
                "WHERE tenant_id = CAST(:t AS uuid) AND event_type = 'asr.transcript' "
                "AND source_ref = :s"
            ),
            {"t": str(tid), "s": f"upload:asr:{upload_id}"},
        ).scalar_one()
    assert int(n_ingest) == 1
