# Break-glass sessions (FR64 — Story 2-7, plumbing only)

## API (platform admin JWT)

- `POST /break-glass/request` — body `{ "tenant_id": "<uuid>", "requested_scope": "tenant_data_read" }`.
- `POST /break-glass/approve/{session_id}` — second `platform_admin` must have a different JWT `sub` than the initiator.
- `DELETE /break-glass/{session_id}` — revokes/ends the session (platform path).

## WebAuthn

- **Production:** send `X-DeployAI-WebAuthn-Assertion` (hardware step-up; Epic 12 will harden the ceremony).
- **Dev / tests only:** `DEPLOYAI_BREAK_GLASS_BYPASS_WEBAUTHN=1` allows omitting the header (never in production config).

## Customer notification + SessionBanner (Epic 12)

- Out of scope for Story 2-7. Schema `break_glass_sessions` and these routes exist so Epic 12 can add notification and UI without re-plumbing the database.

## Audit

- Structured log keys `audit_events.break_glass.*` (see `packages/contracts/schema/audit-events-0.1.0.json`).
