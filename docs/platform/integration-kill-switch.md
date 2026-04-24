# Integration kill-switch (FR14, FR17 — Story 2-6)

## API

- `POST /integrations/{integration_id}/disable` with `Authorization: Bearer` (access JWT).
- Caller must be allowed **`integration:kill_switch`** on the integration’s `tenant_id` (see [role-matrix](../authz/role-matrix.md) — e.g. `deployment_strategist` or `platform_admin`).

## Behavior

- Marks the `integrations` row `state=disabled` and sets `disabled_at`.
- Emits a structured log line `integration.killswitch_triggered` and stub lines for OAuth revoke, SQS (or in-flight) purge, and Secrets Manager deletion. **Epic 3+** will replace stubs with real Microsoft Graph/queue/secret work.

## Environment

- No extra env vars. OAuth/SQS/Secrets wiring land with ingestion (Epic 3).
