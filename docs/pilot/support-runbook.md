# Pilot support runbook

Use during **Epic 16** design partner sessions when something looks wrong.

## Symptom: 403 on `/digest` or strategist APIs

| Check | Action |
| ----- | ------ |
| Missing role | Ensure `x-deployai-role` is set (`deployment_strategist` or allowed role). Production does not inject it. |
| Missing tenant | If `DEPLOYAI_STRATEGIST_REQUIRE_TENANT=1`, set `x-deployai-tenant` to the pilot UUID. |
| Wrong role | Verify authz matrix in `@deployai/authz` for `canonical:read` + `canonical_memory`. |

## Symptom: empty digest / “mock” feel

| Check | Action |
| ----- | ------ |
| No `STRATEGIST_DIGEST_SOURCE_URL` | App uses **code fixtures** unless URL or future CP loader is on—expected. |
| CP digest not wired | Epic 16 loader stories; until then explain fixture vs URL vs CP. |
| Wrong tenant | Confirm `x-deployai-tenant` matches data plane tenant. |

## Symptom: queues disappear after deploy

Expected under **Option B** ([queue-durability-modes.md](./queue-durability-modes.md)). If unacceptable, stop pilot until Option A or freeze deploys.

## Symptom: “in meeting” never shows

| Check | Action |
| ----- | ------ |
| Stub not configured | Set `DEPLOYAI_STUB_IN_MEETING_TENANT_IDS` on CP **or** accept `detection_source: off`. |
| Tenant header mismatch | Web must send same UUID as stub list. |

## Symptom: CP errors in activity banner

| Check | Action |
| ----- | ------ |
| Health | `GET {CP}/healthz` must be `{ "status": "ok" }` before internal routes. |
| Key | `DEPLOYAI_INTERNAL_API_KEY` on web matches CP. |
| Network | Web server can reach CP URL from server-side fetch. |

## Escalation

- **Engineering:** repo owner + CP logs (correlation id when available).
- **Product truth:** [`whats-actually-here.md`](../../whats-actually-here.md).
