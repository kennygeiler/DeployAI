# DeployAI V1 role × capability matrix

This document is the human-facing source for `packages/authz/src/matrix.ts` and `services/_shared/authz/src/deployai_authz/resolver.py`. Change the code and this file together.

| Capability / action | platform_admin | customer_admin | customer_records_officer | deployment_strategist | successor_strategist | external_auditor | pending_assignment |
| ------------------- | :------------: | :------------: | :----------------------: | :-------------------: | :------------------: | :--------------: | :----------------: |
| **ingest:view_runs** | V1 | V1 | V1 | V1 | V1 | — | — |
| **ingest:configure** | V1 | — | — | — | — | — | — |
| **ingest:sync** | V1 | — | — | V1 | — | — | — |
| **integration:kill_switch** | V1 | — | — | V1 | — | — | — |
| **canonical:read** | V1 | V1 | V1 | V1 | V1 | — | — |
| **override:submit** | V1 | V1 | — | V1 | V1 | — | — |
| **admin:view_schema_proposals** | V1 | — | — | — | — | — | — |
| **admin:promote_schema** / **solidification:promote** | V1 | — | — | — | — | — | — |
| **foia:export** | V1 | — | — | — | — | V1⁺¹ | — |
| **scim:manage** | V1 | V1.5 | — | — | — | — | — |
| **break_glass:invoke** | V1 | — | — | — | — | — | — |

**Notes**

- **`pending_assignment`** — issued on first OIDC login before a Platform Admin binds a customer tenant + V1 role (Story 2-2). No matrix actions; `can_access`/`canAccess` deny all capabilities while the user only holds this claim.
- **V1.5** — `customer_admin` and `successor_strategist` are active in product copy; matrix entries marked V1.5 are enforced in the same code path as V1 (no separate build today).
- **⁺¹** — `external_auditor` has **`foia:export`** only for export-oriented APIs (not strategist browser surfaces). **`canonical:read`** is **denied** — Epic 12 Story 12.3: auditors must not read canonical memory via `/digest`, `/evidence/*`, BFF, etc.; future **`/auditor`** audit-evidence routes will use a separate action when implemented.
- **Cross-tenant** — For resources with `kind: "tenant"`, only `platform_admin` may target a tenant id different from `actor.tenantId`.
- **Web (dev)** — `apps/web/middleware.ts` still uses request header `x-deployai-role` for v1. Real SSO and cookies land in Story 2.2 (see [`sprint-status.yaml`](../../_bmad-output/implementation-artifacts/sprint-status.yaml)).

**Related**

- [Architecture — Authorization](../../_bmad-output/planning-artifacts/architecture.md) (search “Authorization”)
- [Epic 2 — Story 2.1](../../_bmad-output/planning-artifacts/epics.md) (search “Story 2.1”)
- RLS session GUC: [rls-alignment.md](./rls-alignment.md)
