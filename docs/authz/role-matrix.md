# DeployAI V1 role × capability matrix

This document is the human-facing source for `packages/authz/src/matrix.ts` and `services/_shared/authz/src/deployai_authz/resolver.py`. Change the code and this file together.

| Capability / action | platform_admin | customer_admin | customer_records_officer | deployment_strategist | fde | biz_dev | demo_guest | successor_strategist | external_auditor | pending_assignment |
| ------------------- | :------------: | :------------: | :----------------------: | :-------------------: | :-: | :-----: | :--------: | :------------------: | :--------------: | :----------------: |
| **ingest:view_runs** | V1 | V1 | V1 | V1 | V1 | — | — | V1 | — | — |
| **ingest:configure** | V1 | — | — | — | — | — | — | — | — | — |
| **ingest:sync** | V1 | — | — | V1 | V1 | — | — | — | — | — |
| **integration:kill_switch** | V1 | — | — | V1 | V1 | — | — | — | — | — |
| **canonical:read** | V1 | V1 | V1 | V1 | V1 | V1 | V1 | V1 | — | — |
| **override:submit** | V1 | V1 | — | V1 | V1 | — | — | V1 | — | — |
| **admin:view_schema_proposals** | V1 | — | — | — | — | — | — | — | — | — |
| **admin:promote_schema** / **solidification:promote** | V1 | — | — | — | — | — | — | — | — | — |
| **foia:export** | V1 | — | — | — | — | — | — | — | V1⁺¹ | — |
| **scim:manage** | V1 | V1.5 | — | — | — | — | — | — | — | — |
| **break_glass:invoke** | V1 | — | — | — | — | — | — | — | — | — |

**Notes**

- **`pending_assignment`** — issued on first OIDC login before a Platform Admin binds a customer tenant + V1 role (Story 2-2). No matrix actions; `can_access`/`canAccess` deny all capabilities while the user only holds this claim.
- **`fde`** (Forward Deployed Engineer) and **`biz_dev`** — team roles added during the team-tracking pivot (see archived `docs/archive/product/deployai-source-of-truth-spec.md` §16 for historical context). `fde` is operationally equivalent to `deployment_strategist` (both run the engagement). `biz_dev` has least-privilege `canonical:read` only for now.
- **`demo_guest`** — public "View live demo" sessions (Wave 4S). Minted only by the control plane's `POST /internal/v1/demo/session` (requires the internal key + `DEPLOYAI_DEMO_GUEST_ENABLED=1` + `DEPLOYAI_DEMO_TENANT_ID`), always onto a disposable demo tenant. `canonical:read` only: strategist read surfaces + Oracle chat work; `/admin` (`admin:read`) and `/api/internal/v1` proxy routes (`internal:proxy` — bulk proposal accept, MCP config, Agent Kenny dashboard) are denied at the web middleware. Known residual risk: BFF mutation routes that gate with `canonical:read` today (single proposal accept/reject, review-item resolve/dismiss, insight actions, onboarding seeds) remain callable by `demo_guest`; writes are confined to the disposable demo tenant by the cross-tenant rule + RLS. Never enable demo mode on a deployment holding customer tenants.
- **V1.5** — `customer_admin` and `successor_strategist` are active in product copy; matrix entries marked V1.5 are enforced in the same code path as V1 (no separate build today).
- **⁺¹** — `external_auditor` has **`foia:export`** only for export-oriented APIs (not strategist browser surfaces). **`canonical:read`** is **denied** — Epic 12 Story 12.3: auditors must not read canonical memory via `/digest`, `/evidence/*`, BFF, etc.; future **`/auditor`** audit-evidence routes will use a separate action when implemented.
- **Cross-tenant** — For resources with `kind: "tenant"`, only `platform_admin` may target a tenant id different from `actor.tenantId`.
- **Web (dev)** — `apps/web/middleware.ts` still uses request header `x-deployai-role` for v1. Real SSO and cookies land later (historical delivery context: archived [`delivery-status.yaml`](../archive/delivery-status.yaml)).

**Related**

- [Architecture — Authorization](../archive/architecture.md) (archived; search “Authorization”)
- [Epic 2 — Story 2.1](../archive/epics.md) (archived; search “Story 2.1”)
- RLS session GUC: [rls-alignment.md](./rls-alignment.md)
