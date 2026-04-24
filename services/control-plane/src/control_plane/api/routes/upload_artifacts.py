"""Direct-to-S3 presigned upload (Epic 3 Story 3-4, FR12)."""

from __future__ import annotations

import uuid
from typing import Annotated

from deployai_authz import AuthActor, can_access
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from control_plane.api.jwt_actor import bearer_auth_actor
from control_plane.exceptions import UploadPresignNotConfiguredError
from control_plane.services.upload_artifact_ingest import complete_meeting_artifact
from control_plane.services.upload_artifact_s3 import presign_meeting_artifact

router = APIRouter(prefix="/upload/artifacts", tags=["upload-artifacts"])


class PresignUploadRequest(BaseModel):
    """Request a short-lived S3 ``POST /`` policy for a single file (browser then uploads directly)."""

    tenant_id: uuid.UUID = Field(description="Account (DeployAI) tenant; must match the strategist token")
    filename: str = Field(min_length=1, max_length=512, examples=["call-notes.m4a"])
    content_type: str = Field(min_length=1, max_length=128, examples=["audio/mp4"])
    file_size: int = Field(ge=1, le=500 * 1024 * 1024, description="Declared byte size of the file (≤ 500 MB)")


class PresignUploadResponse(BaseModel):
    upload_url: str
    form_fields: dict[str, str]
    object_key: str
    upload_id: str
    expires_in: int = 3600


class CompleteUploadRequest(BaseModel):
    """After S3 POST succeeds, record consent + metadata and create ``upload.transcript`` (tenant-scoped)."""

    tenant_id: uuid.UUID
    object_key: str = Field(min_length=8, max_length=1024)
    upload_id: uuid.UUID = Field(description="Must match the upload_id from /presign")
    consent_two_party: bool = Field(
        description="Attestation that two-party (or stricter) recording rules were satisfied (NFR39)"
    )
    recording_jurisdiction: str = Field(
        min_length=2,
        max_length=128,
        description="E.g. US-CA, EU; captured for NFR39 compliance metadata",
    )


class CompleteUploadResponse(BaseModel):
    inserted: int
    idempotent: bool = False
    source_ref: str
    queue_dispatched: bool = False
    """``True`` when a transcribe job was sent to ``DEPLOYAI_INGEST_UPLOAD_SQS_URL`` (best-effort)."""


def _resolve_tenant(actor: AuthActor, body: PresignUploadRequest) -> uuid.UUID:
    if actor.role == "platform_admin":
        return body.tenant_id
    if not actor.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access token is missing tid for this action",
        )
    if str(body.tenant_id) != str(actor.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_id does not match token",
        )
    return body.tenant_id


def _resolve_tenant_complete(actor: AuthActor, body: CompleteUploadRequest) -> uuid.UUID:
    if actor.role == "platform_admin":
        return body.tenant_id
    if not actor.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Access token is missing tid for this action",
        )
    if str(body.tenant_id) != str(actor.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="tenant_id does not match token",
        )
    return body.tenant_id


@router.post(
    "/presign",
    response_model=PresignUploadResponse,
    summary="Mint S3 presigned POST for a meeting/voice file (direct browser upload)",
)
async def presign_artifact_upload(
    body: PresignUploadRequest,
    actor: Annotated[AuthActor, Depends(bearer_auth_actor)],
) -> PresignUploadResponse:
    tid = _resolve_tenant(actor, body)
    d = can_access(
        actor,
        "ingest:sync",
        {"kind": "tenant", "id": str(tid)},
        skip_audit=False,
    )
    if not d.allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=d.reason)
    try:
        r = presign_meeting_artifact(
            tenant_id=tid,
            filename=body.filename,
            content_type=body.content_type,
            file_size=body.file_size,
        )
    except UploadPresignNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Upload presign is not configured (set DEPLOYAI_UPLOAD_ARTIFACT_S3_BUCKET and AWS creds).",
        ) from None
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return PresignUploadResponse(
        upload_url=r.url,
        form_fields=r.form_fields,
        object_key=r.object_key,
        upload_id=r.upload_id,
        expires_in=r.expires_in,
    )


@router.post(
    "/complete",
    response_model=CompleteUploadResponse,
    summary="Record consent + S3 key after direct upload; emit upload.transcript (stub ASR for now)",
)
async def complete_artifact_upload(
    body: CompleteUploadRequest,
    actor: Annotated[AuthActor, Depends(bearer_auth_actor)],
) -> CompleteUploadResponse:
    tid = _resolve_tenant_complete(actor, body)
    d = can_access(
        actor,
        "ingest:sync",
        {"kind": "tenant", "id": str(tid)},
        skip_audit=False,
    )
    if not d.allow:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=d.reason)
    try:
        r = await complete_meeting_artifact(
            tenant_id=tid,
            object_key=body.object_key,
            upload_id=body.upload_id,
            consent_two_party=body.consent_two_party,
            recording_jurisdiction=body.recording_jurisdiction,
        )
    except UploadPresignNotConfiguredError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="S3 is not configured for upload finalization (same bucket as presign).",
        ) from None
    except FileNotFoundError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e) or "S3 object not found",
        ) from e
    except PermissionError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e) or "S3 access error while verifying the uploaded object.",
        ) from e
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e
    return CompleteUploadResponse(
        inserted=int(r.get("inserted", 0)),
        idempotent=bool(r.get("idempotent")),
        source_ref=str(r.get("source_ref", "")),
        queue_dispatched=bool(r.get("queue_dispatched")),
    )
