import type { Action } from "./types.js";
import type { V1Role } from "./roles.js";

/** Role × action allow-list (Epic 2.1; human table in docs/authz/role-matrix.md). */
const can: Array<[V1Role, Action]> = [
  ["platform_admin", "ingest:view_runs"],
  ["platform_admin", "ingest:configure"],
  ["platform_admin", "ingest:sync"],
  ["platform_admin", "integration:kill_switch"],
  ["platform_admin", "admin:view_schema_proposals"],
  ["platform_admin", "admin:promote_schema"],
  ["platform_admin", "foia:export"],
  ["platform_admin", "canonical:read"],
  ["platform_admin", "override:submit"],
  ["platform_admin", "solidification:promote"],
  ["platform_admin", "break_glass:invoke"],
  ["platform_admin", "scim:manage"],
  ["platform_admin", "eval:view_adjudication"],
  ["customer_admin", "ingest:view_runs"],
  ["customer_admin", "canonical:read"],
  ["customer_admin", "override:submit"],
  ["customer_admin", "scim:manage"],
  ["customer_admin", "eval:view_adjudication"],
  ["customer_records_officer", "ingest:view_runs"],
  ["customer_records_officer", "canonical:read"],
  ["external_auditor", "foia:export"],
  ["deployment_strategist", "ingest:view_runs"],
  ["deployment_strategist", "ingest:sync"],
  ["deployment_strategist", "integration:kill_switch"],
  ["deployment_strategist", "canonical:read"],
  ["deployment_strategist", "override:submit"],
  ["deployment_strategist", "eval:view_adjudication"],
  ["successor_strategist", "ingest:view_runs"],
  ["successor_strategist", "canonical:read"],
  ["successor_strategist", "override:submit"],
  ["successor_strategist", "eval:view_adjudication"],
];

const key = (role: V1Role, a: Action) => `${role}::${a}`;

const allowSet = new Set<string>(can.map(([r, a]) => key(r, a)));

export function isAllowedByMatrix(role: V1Role, action: Action): boolean {
  return allowSet.has(key(role, action));
}
