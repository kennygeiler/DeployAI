# Story 3.1: M365 Calendar OAuth ingestion (FR9)

Status: **done** (2026-04-24) — Microsoft Graph **delegated OAuth** + **`calendarView/delta`**, idempotent `canonical_memory_events` writes, **integration E2E** (mocked IdP/Graph). CI gate runs the M365 integration file.

## Story (from [epics.md](../planning-artifacts/epics.md) §3.1)

As a **Deployment Strategist**,
I want to ingest calendar events from Microsoft 365 Calendar via authenticated OAuth,
So that every meeting becomes a canonical event with no manual data entry (FR9).

## Completion notes (what shipped)

- **Routes:** `GET /integrations/m365-calendar/connect` (Bearer, `ingest:sync`), `GET /callback` (cookie-bound PKCE + state; **validated `return_to`** to block open redirects), `POST /integrations/m365-calendar/{id}/sync`.
- **OAuth:** Scopes for Graph `Calendars.Read` + `User.Read` + `offline_access`; `DEPLOYAI_M365_*` with **fallback to** `DEPLOYAI_OIDC_*` where unset; integration row uses **DB-valid** `state` (`active` default — `pending_oauth` is **not** a valid check constraint; OAuth-pending = missing `config.oauth` tokens).
- **Sync:** Graph **delta** (initial window + `graph.delta_link`); inserts `event_type=calendar.event`, `source_ref=graph:calendar_event:{id}`, idempotent re-sync.
- **Tests:** `tests/unit/test_m365_calendar_routes.py`, `tests/integration/test_m365_calendar_flow.py` (E2E with mocked Microsoft HTTP).
- **Docs / env:** `services/control-plane/README.md` (how to run integration tests), root `.env.example` M365 block.

## Intentional deferrals (covered by other stories / infra, not 3-1)

| Epics / AC (original text) | Where it lands |
|----------------------------|----------------|
| **RFC 3161 signed timestamp** on each calendar event | Canonical substrate uses **row `created_at`**; RFC 3161 TSA is **tombstone / attestation** class work (per architecture). Follow-up: attach signed envelope when the global stamping pipeline exists. |
| **SQS** queue, **72h** retention, **exponential backoff** worker | **Story 3-6** (idempotent + DLQ) + **workers/infra** — control-plane v1 is **synchronous pull on `/sync`**. |
| **Graph 429** throttling, load tests, “2500 events/hour” | **Story 3-7** (throttling / token bucket). |
| **Integration tests: 20 events, 72h recovery** | Partially satisfied by **idempotent** + **delta** tests; full soak / chaos → **3-6 / 3-7** or dedicated load job. |

## File list (primary)

- `services/control-plane/src/control_plane/api/routes/integrations_m365_calendar.py`
- `services/control-plane/src/control_plane/integrations/m365_oauth.py`
- `services/control-plane/src/control_plane/services/m365_calendar_sync.py`
- `services/control-plane/src/control_plane/main.py` (router include)
- `services/control-plane/tests/integration/test_m365_calendar_flow.py`
- `services/control-plane/tests/unit/test_m365_calendar_routes.py`
- `services/control-plane/src/control_plane/config/settings.py` (M365 env)

**References:** [epics.md](../planning-artifacts/epics.md) · FR9
