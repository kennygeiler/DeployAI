# Epic 3 retrospective — Ingestion Pipelines

**Date:** 2026-04-23 · **Sprint ref:** `sprint-status.yaml` (epic-3: done)

## Outcomes

- **M365:** Calendar, Exchange mail, and Teams transcript flows are implemented with **Graph**-backed sync, throttling token bucket, and **ingestion run** telemetry; integration tests cover OAuth + mocked Graph (`test_m365_*_flow.py`).
- **Other channels:** Gmail and Slack paths exist in the codebase; extend integration coverage as those routes stabilize.
- **FR16 / FR18 / FR19:** Extraction unit validation (`ingest/validators.py`), idempotent canonical writes (`ingestion_dedup_key`), and `graph_ingest_rps` are shipped and under test.
- **Voice / upload (3-4):** Presigned S3 upload, `upload.transcript` + optional **SQS** job, **worker** producing **`asr.transcript`** with dedup; full path covered in `test_upload_artifact_flow.py`.
- **CI:** The complete control-plane `tests/integration/` suite runs on every PR to `main` (job **Control plane (integration)**).

## What worked well

- **Append-only canonical model** led to a clean pattern for ASR: new event type + dedup key instead of mutating an existing row.
- **Moto** for S3/SQS in tests kept AWS-dependent paths fast and deterministic.
- **Single integration command** for developers (`env PYTEST_ADDOPTS= uv run pytest tests/integration/ -m integration`) matches CI.

## Learnings and risks

- **Real cloud OAuth** and **long-running workers** (SQS, Transcribe) need staging accounts; tests use mocks, not live Microsoft or AWS ASR.
- **Path-filtered** `schema` and `fuzz` jobs do not run on every PR; promoting them to **required** improves safety when they run, but **docs- or design-only** PRs may show those checks as skipped—configure branch rules accordingly.
- **Operator UX** (upload surface, admin surfaces for runs) lags the API; see deferred backlog.

## Action items (see also `deferred-work.md` §Epic 3)

| Item | Note |
|------|------|
| First-party **web upload** UX | Beyond stub API |
| **AWS Transcribe** (or other ASR) in worker when `upload_asr_mode=transcribe` | Today: stub + log line |
| **S3 lifecycle** for raw object retention (NFR33) | Infra / bucket policy |
| **Citation E2E** from `upload.transcript` / `asr.transcript` | Downstream Cartographer / extraction |
| Ingestion **observability** dashboards | Epic 12 / ops stories |

## Next epic handoff

Epic 4 (agent runtime, replay) should treat canonical events as **read-only** inputs and preserve citation envelope invariants; ingestion remains the only writer for provider-pulled and upload-pipeline events.
