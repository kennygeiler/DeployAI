# Story 3.4: Voice / meeting file upload (FR12, NFR39)

Status: **done** (2026-04-23) for API + async path: presign, `/complete` with consent + jurisdiction, stub `upload.transcript`, optional **SQS** job on complete (`DEPLOYAI_INGEST_UPLOAD_SQS_URL`), **worker** `python -m control_plane.workers.transcribe_upload` that appends idempotent **asr.transcript** (stub ASR text; `DEPLOYAI_UPLOAD_ASR_MODE=transcribe` is reserved for real AWS Transcribe later). **Follow-ups (not in this story):** web `/upload` UI, 90-day S3 lifecycle, citation E2E.

## Shipped in this slice

- **API:** `POST /upload/artifacts/presign` (Bearer) → `{ upload_url, form_fields, object_key, upload_id, expires_in }` for direct browser `multipart/form-data` to S3 (no file bytes through control plane).
- **API:** `POST /upload/artifacts/complete` (Bearer) with `consent_two_party` + `recording_jurisdiction` → `upload.transcript` (placeholder body) + best-effort SQS + `queue_dispatched` in the JSON.
- **Worker:** `control_plane.workers.transcribe_upload` long-poll SQS; `asr.transcript` session event with `ingestion_dedup_key` (append-only, idempotent redelivery).
- **Config:** `DEPLOYAI_UPLOAD_ARTIFACT_S3_*`, `DEPLOYAI_INGEST_UPLOAD_SQS_URL`, `DEPLOYAI_UPLOAD_ASR_MODE`, AWS creds; `.env.example` block.
- **Service:** `upload_artifact_s3.py` — validation + `boto3` `generate_presigned_post` with `content-length-range` and `Content-Type` condition; `sqs_transcribe_job` + `upload_artifact_ingest`.
- **Ingest:** `asr.transcript` is a **session** extraction unit (see `ingest/validators.py`).
- **Tests:** `tests/unit/test_upload_artifact_s3.py`; `tests/integration/test_upload_artifact_flow.py` (S3 + SQS + worker → DB).

## Remaining (same story / follow-ups)

| AC fragment | Plan |
|-------------|------|
| Web UX | First-party `/upload` or edge-agent wiring |
| Real ASR | AWS Transcribe (or other) in worker when `upload_asr_mode=transcribe` |
| 90-day raw retention (NFR33) | S3 lifecycle rule or post-ingest job |
| Citation E2E | After extraction consumes `asr.transcript` / `upload.transcript` |

**References:** [epics.md](../planning-artifacts/epics.md) · FR12
