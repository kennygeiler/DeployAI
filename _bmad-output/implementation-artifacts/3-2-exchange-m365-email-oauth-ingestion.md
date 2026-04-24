# Story 3.2: Exchange / M365 Email OAuth ingestion (FR10)

Status: **in-progress** (2026-04-24) — Picked up after [3-1 M365 calendar](3-1-m365-calendar-oauth-ingestion.md) **done**. Implementation not started in this change.

## Story (from [epics.md](../planning-artifacts/epics.md) §3.2)

As a **Deployment Strategist**,
I want to ingest email from Exchange / M365 via authenticated OAuth,
So that email threads become canonical events at the **thread-level** unit of extraction (FR10, FR16).

## Acceptance criteria (epic)

- Graph pull for **thread** (not per-message) → `event_type = 'email.thread'`
- Bodies in **S3** (tenant prefix) + `body_ref` in payload
- **Delta** + idempotent writes
- Tests: new thread, thread update, throttled retry

## Build on 3-1

- Reuse patterns: `integrations` model, Entra app / OAuth, `ingest:sync` authz, canonical `source_ref` / idempotency, Graph HTTP client + settings.

## File list

_(Populated on implementation.)_

**References:** [epics.md](../planning-artifacts/epics.md) · FR10 · FR16
