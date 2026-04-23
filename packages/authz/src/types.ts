import type { V1Role } from "./roles.js";

export type Action =
  | "ingest:view_runs"
  | "ingest:configure"
  | "admin:view_schema_proposals"
  | "admin:promote_schema"
  | "foia:export";

export type Resource =
  | { kind: "ingestion_runs" }
  | { kind: "schema_proposals" }
  | { kind: "tenant"; id: string };

export type Decision =
  | { allow: true }
  | { allow: false; reason: string; code: "forbidden" | "unauthenticated" };

export type AuthActor = { role: V1Role; tenantId?: string };

export type AuthzResolver = (
  actor: AuthActor,
  action: Action,
  resource: Resource,
) => Promise<Decision> | Decision;
