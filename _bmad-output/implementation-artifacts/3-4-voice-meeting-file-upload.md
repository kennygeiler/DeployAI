# Story 3.4: Voice / meeting file upload (FR12, NFR39)

Status: **in progress** (2026-04-23) — **S3 presigned POST** via control plane (`POST /upload/artifacts/presign`) is implemented: strategist token + `ingest:sync` on tenant, ≤500 MB, `.mp3/.m4a/.mp4/.wav`, moto-bucket unit tests. **Not yet done:** web `/upload` UI, two-party **consent** + NFR39 **jurisdiction** capture, **SQS** + transcribe + `upload.transcript` canonical event, 90-day retention job, citation-envelope E2E.

## Shipped in this slice

- **API:** `POST /upload/artifacts/presign` (Bearer) → `{ upload_url, form_fields, object_key, upload_id, expires_in }` for direct browser `multipart/form-data` to S3 (no file bytes through control plane).
- **Config:** `DEPLOYAI_UPLOAD_ARTIFACT_S3_*` + AWS credential chain; `.env.example` block.
- **Service:** `upload_artifact_s3.py` — validation + `boto3` `generate_presigned_post` with `content-length-range` and `Content-Type` condition.
- **Tests:** `tests/unit/test_upload_artifact_s3.py` (moto, JWT ASGI, 503 when bucket unset).
- **Dependencies:** `boto3` (runtime), `moto[s3]` (dev).

## Remaining (same story / follow-ups)

| AC fragment | Plan |
|-------------|------|
| Consent + jurisdiction | Web form + optional fields on complete-upload callback |
| SQS + Whisper / Transcribe | Worker + `upload.transcript` event |
| 90-day raw retention (NFR33) | Lifecycle rule or post-ingest job |
| Integration: upload → transcribe → canonical + citation | End-to-end after worker |

**References:** [epics.md](../planning-artifacts/epics.md) · FR12
