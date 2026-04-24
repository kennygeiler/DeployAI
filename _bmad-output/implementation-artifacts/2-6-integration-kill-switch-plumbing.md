# Story 2.6: Integration kill-switch plumbing (FR14, FR17, NFR24)

Status: done

## Summary

- `POST /integrations/{integration_id}/disable` with JWT + `integration:kill_switch` authz (`deployai_authz.can_access` on tenant resource).
- Alembic `20260428_0006`: `integrations` table; stub logs for OAuth revoke, queue purge, Secrets delete; structured `integration.killswitch_triggered`.
- Docs: `docs/platform/integration-kill-switch.md`

## Deferred (Epic 3+)

- Real Microsoft Graph token revoke, SQS purge, Secrets Manager deletion, wall-clock ≤30s SLO on reference stack.
