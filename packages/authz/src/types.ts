import type { V1Role } from "./roles.js";

/**
 * Fine-grained actions (domain:capability). Legacy `ingest:*` / `admin:*` from Story 1-16/17
 * are preserved; Epic 2.1 adds matrix rows for future surfaces (canonical, override, …).
 */
export type Action =
  | "ingest:view_runs"
  | "ingest:configure"
  | "ingest:sync"
  | "integration:kill_switch"
  | "admin:view_schema_proposals"
  | "admin:promote_schema"
  | "foia:export"
  | "canonical:read"
  | "override:submit"
  | "solidification:promote"
  | "break_glass:invoke"
  | "scim:manage";

export type Resource =
  | { kind: "ingestion_runs" }
  | { kind: "schema_proposals" }
  | { kind: "tenant"; id: string }
  | { kind: "canonical_memory" }
  | { kind: "override" }
  | { kind: "foia_export" }
  | { kind: "break_glass" }
  | { kind: "scim" }
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
