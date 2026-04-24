# Story 2.7: Break-glass plumbing (FR64 infrastructure; E2E Epic 12)

Status: done

## Summary

- Alembic `20260428_0006`: `break_glass_sessions` with status workflow.
- `POST /break-glass/request`, `POST /break-glass/approve/{id}`, `DELETE /break-glass/{id}` — all `require_platform_admin`, WebAuthn header unless `DEPLOYAI_BREAK_GLASS_BYPASS_WEBAUTHN=1` (dev/tests).
- Dual approval: approver JWT `sub` ≠ initiator `sub`.
- Audit log keys `audit_events.break_glass.*`; contract list in `packages/contracts/schema/audit-events-0.1.0.json`.
- Docs: `docs/platform/break-glass.md`

## Deferred (Epic 12)

- Customer notification, SessionBanner, IAM IC hook, full WebAuthn ceremony, RFC 3161 on log lines.
