import type { Action } from "./types.js";
import type { V1Role } from "./roles.js";

/** Minimal role × action (Story 1-14, expanded in Epic 2.1 + docs/authz/role-matrix.md). */
const can: Array<[V1Role, Action]> = [
  ["platform_admin", "ingest:view_runs"],
  ["platform_admin", "ingest:configure"],
  ["platform_admin", "admin:view_schema_proposals"],
  ["platform_admin", "admin:promote_schema"],
  ["platform_admin", "foia:export"],
  ["customer_admin", "ingest:view_runs"],
  ["customer_records_officer", "ingest:view_runs"],
  ["external_auditor", "foia:export"],
  ["deployment_strategist", "ingest:view_runs"],
  ["successor_strategist", "ingest:view_runs"],
];

const key = (role: V1Role, a: Action) => `${role}::${a}`;

const allowSet = new Set<string>(can.map(([r, a]) => key(r, a)));

export function isAllowedByMatrix(role: V1Role, action: Action): boolean {
  return allowSet.has(key(role, action));
}
