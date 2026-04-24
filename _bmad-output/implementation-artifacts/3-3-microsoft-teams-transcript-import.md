# Story 3.3: Microsoft Teams transcript import (FR11)

Status: **done** (2026-04-23) — Microsoft Graph **delegated OAuth** (Calendars + OnlineMeetings + Transcript) + **calendarView/delta** to discover **online meeting** events, resolve **meeting id** by `JoinWebUrl` filter, list **callTranscript**, fetch **VTT** content, idempotent `meeting.transcript` canonical events; **stub** transcript file refs; **identity** email match + **candidates** from VTT speakers; **chunking** for sessions ≥ 60 min; integration E2E with mocked Graph.

## Completion notes (what shipped)

- **Routes:** `GET /integrations/m365-teams/connect`, `GET /callback`, `POST /integrations/m365-teams/{id}/sync` (same auth/cookie pattern as 3-1/3-2, path `/integrations/m365-teams`).
- **OAuth:** `GRAPH_TEAMS_SCOPES` — `User.Read`, `Calendars.Read`, `OnlineMeetings.Read`, `OnlineMeetingTranscript.Read.All`, `offline_access`; `DEPLOYAI_M365_TEAMS_REDIRECT_URI` + M365 or OIDC client triple.
- **Sync:** `calendarView/delta` (stores `graph.teams_calendar_delta_link`); for each ended `isOnlineMeeting` event with `onlineMeeting.joinUrl` → `GET /me/onlineMeetings?$filter=JoinWebUrl eq '...'` → `GET .../transcripts` → latest transcript → `GET .../transcripts/{id}/content` (VTT); `source_ref=graph:meeting_transcript:{transcript_id}`.
- **Payload:** `meeting.transcript` session unit — `transcript_chunks` (with `transcript_ref` stub URLs), `participants` (attendee email + optional `identity_id` when `identity_nodes.primary_email_hash` matches), `identity_resolution_candidates` (VTT speaker names not in attendee display names).
- **Tests:** `test_m365_teams_routes.py`, `test_m365_teams_transcript_unit.py`, `test_m365_teams_flow.py` (E2E + identity match + idempotent second sync).
- **Env:** root `.env.example` Teams block.

## Intentional deferrals

| Area | Notes |
|------|--------|
| S3 for VTT / long-term artifact store | Reuses `ingest_email_body_mode=stub` and shared stub root dir. |
| SQS / async pull | Remains **sync** on `POST /sync` (3-6+). |
| Throttling 429 | Basic retry in `\_graph_get` only; 3-7. |
| RSC / application-only meeting policies | Delegated v1 only. |

## File list (primary)

- `services/control-plane/src/control_plane/api/routes/integrations_m365_teams.py`
- `services/control-plane/src/control_plane/services/m365_teams_transcript_sync.py`
- `services/control-plane/src/control_plane/infra/transcript_artifact_store.py`
- `services/control-plane/src/control_plane/integrations/m365_oauth.py` (scopes + `m365_teams_oauth_creds`)
- `services/control-plane/src/control_plane/config/settings.py` — `m365_teams_redirect_uri`
- `services/control-plane/src/control_plane/main.py` — router include
- `services/control-plane/tests/.../test_m365_teams_*.py`

**References:** [epics.md](../planning-artifacts/epics.md) · FR11
