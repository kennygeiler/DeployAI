import type { V1Role } from "./roles.js";

/**
 * Fine-grained actions (domain:capability). Legacy `ingest:*` / `admin:*` from Story 1-16/17
 * are preserved; Epic 2.1 adds matrix rows for future surfaces (canonical, override, …).
 * Wave 1 (ticket A5) adds `admin:read` (strategist-shell /admin pages) and
 * `internal:proxy` (web BFF /api/internal/v1 proxy routes).
 */
export type Action =
  | "ingest:view_runs"
  | "ingest:configure"
  | "ingest:sync"
  | "integration:kill_switch"
  | "admin:view_schema_proposals"
  | "admin:promote_schema"
  | "admin:read"
  | "internal:proxy"
  | "foia:export"
  | "canonical:read"
  | "override:submit"
  | "solidification:promote"
  | "break_glass:invoke"
  | "scim:manage"
  | "eval:view_adjudication";

/**
 * Every resource may carry the tenant it belongs to. `canAccess` blocks whenever the
 * actor's tenant and the resource's tenant are both present and differ (any kind).
 * For `kind: "tenant"` the resource IS the tenant, so `id` doubles as the tenant id.
 *
 * `canonical_memory`, `override`, and `foia_export` are tenant-scoped kinds: callers
 * MUST supply `tenantId` (see `canAccess` for how omission is handled).
 */
export type Resource =
  | { kind: "ingestion_runs"; tenantId?: string }
  | { kind: "schema_proposals"; tenantId?: string }
  | { kind: "tenant"; id: string }
  | { kind: "canonical_memory"; tenantId?: string }
  | { kind: "override"; tenantId?: string }
  | { kind: "foia_export"; tenantId?: string }
  | { kind: "break_glass"; tenantId?: string }
  | { kind: "scim"; tenantId?: string }
  | { kind: "global" };

export type Decision =
  | { allow: true; code: "ok" }
  | { allow: false; reason: string; code: "forbidden" | "unauthenticated" };

export type AuthActor = { role: V1Role; tenantId?: string };

export type AuthzResolver = (
  actor: AuthActor,
  action: Action,
  resource: Resource,
) => Promise<Decision> | Decision;

export type AuthzAuditEvent = {
  event: "authz_decision";
  allow: boolean;
  actor_role: V1Role;
  action: Action;
  resource_kind: string;
  tenant_id: string | null;
  resource_tenant_id: string | null;
  code: "ok" | "forbidden" | "unauthenticated";
  reason?: string;
  trace_id?: string;
};
