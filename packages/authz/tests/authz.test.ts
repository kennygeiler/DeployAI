import { describe, expect, it } from "vitest";

import { canAccess } from "../src/can-access.js";
import { isAllowedByMatrix } from "../src/matrix.js";
import type { Action } from "../src/types.js";
import type { V1Role } from "../src/roles.js";

const global = { kind: "global" as const };
const opts = { skipAudit: true as const };

describe("canAccess + matrix (Epic 2.1)", () => {
  it("platform_admin allows promote on global resource", () => {
    const d = canAccess(
      { role: "platform_admin" },
      "admin:promote_schema",
      { kind: "schema_proposals" },
      opts,
    );
    expect(d).toEqual({ allow: true, code: "ok" });
  });

  it("external_auditor cannot promote", () => {
    const d = canAccess(
      { role: "external_auditor" },
      "admin:promote_schema",
      { kind: "schema_proposals" },
      opts,
    );
    expect(d.allow).toBe(false);
    expect(d.allow === false && d.code).toBe("forbidden");
  });

  it("cross-tenant blocked for customer_admin", () => {
    const d = canAccess(
      { role: "customer_admin", tenantId: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" },
      "canonical:read",
      { kind: "tenant", id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" },
      opts,
    );
    expect(d.allow).toBe(false);
  });

  it("platform_admin may access any tenant resource", () => {
    const d = canAccess(
      { role: "platform_admin" },
      "canonical:read",
      { kind: "tenant", id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" },
      opts,
    );
    expect(d.allow).toBe(true);
  });

  it.each<[V1Role, Action, boolean]>([
    ["deployment_strategist", "ingest:view_runs", true],
    ["deployment_strategist", "integration:kill_switch", true],
    ["deployment_strategist", "break_glass:invoke", false],
    ["customer_admin", "scim:manage", true],
    ["customer_admin", "break_glass:invoke", false],
    ["customer_records_officer", "canonical:read", true],
    ["customer_records_officer", "scim:manage", false],
    ["successor_strategist", "override:submit", true],
    ["external_auditor", "foia:export", true],
    ["external_auditor", "ingest:view_runs", false],
    ["deployment_strategist", "eval:view_adjudication", true],
    ["external_auditor", "eval:view_adjudication", false],
  ])("role %s action %s -> %s", (role, action, expectAllow) => {
    const d = canAccess({ role }, action, global, opts);
    expect(d.allow).toBe(expectAllow);
  });

  it("isAllowedByMatrix matches canAccess on global resource", () => {
    const role: V1Role = "platform_admin";
    const action: Action = "ingest:sync";
    expect(isAllowedByMatrix(role, action)).toBe(true);
    expect(canAccess({ role }, action, global, opts).allow).toBe(true);
  });
});
