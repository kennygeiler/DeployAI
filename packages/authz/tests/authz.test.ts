import { afterEach, describe, expect, it, vi } from "vitest";

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
    ["external_auditor", "canonical:read", false],
    ["external_auditor", "ingest:view_runs", false],
    ["deployment_strategist", "eval:view_adjudication", true],
    ["external_auditor", "eval:view_adjudication", false],
    ["fde", "canonical:read", true],
    ["fde", "integration:kill_switch", true],
    ["fde", "break_glass:invoke", false],
    ["biz_dev", "canonical:read", true],
    ["biz_dev", "override:submit", false],
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

describe("tenant comparison on every resource kind (Wave 1 ticket A5)", () => {
  const T_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";
  const T_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";

  it.each<[V1Role, Action, string | undefined, string, boolean]>([
    // [actor role, action, actor tenant, resource tenant, expect allow]
    ["deployment_strategist", "canonical:read", T_A, T_A, true],
    ["deployment_strategist", "canonical:read", T_A, T_B, false],
    ["customer_admin", "canonical:read", T_A, T_B, false],
    ["fde", "override:submit", T_A, T_B, false],
    ["external_auditor", "foia:export", T_A, T_A, true],
    ["external_auditor", "foia:export", T_A, T_B, false],
    // platform_admin is exempt from the cross-tenant block (support/ops role)
    ["platform_admin", "canonical:read", T_A, T_B, true],
    // actor without a tenant: only the both-present-and-differ rule applies,
    // so non-tenant kinds fall through to the matrix
    ["deployment_strategist", "canonical:read", undefined, T_A, true],
  ])(
    "role %s action %s actorTenant %s resourceTenant %s -> %s",
    (role, action, actorTenant, resTenant, expectAllow) => {
      const kind =
        action === "foia:export" ? ("foia_export" as const) : ("canonical_memory" as const);
      const actor = actorTenant === undefined ? { role } : { role, tenantId: actorTenant };
      const d = canAccess(actor, action, { kind, tenantId: resTenant }, opts);
      expect(d.allow).toBe(expectAllow);
      if (!expectAllow) {
        expect(d.allow === false && d.code).toBe("forbidden");
      }
    },
  );

  it("cross-tenant block applies to the override kind too", () => {
    const d = canAccess(
      { role: "successor_strategist", tenantId: T_A },
      "override:submit",
      { kind: "override", tenantId: T_B },
      opts,
    );
    expect(d.allow).toBe(false);
  });
});

describe("tenant-scoped kinds without tenantId are a policy error (Wave 1 ticket A5)", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it.each(["canonical_memory", "override", "foia_export"] as const)(
    "throws outside production for kind %s",
    (kind) => {
      expect(() =>
        canAccess({ role: "platform_admin", tenantId: "t1" }, "canonical:read", { kind }, opts),
      ).toThrow(/tenant-scoped/);
    },
  );

  it("denies fail-closed in production", () => {
    vi.stubEnv("NODE_ENV", "production");
    const d = canAccess(
      { role: "deployment_strategist", tenantId: "t1" },
      "canonical:read",
      { kind: "canonical_memory" },
      opts,
    );
    expect(d.allow).toBe(false);
    expect(d.allow === false && d.reason).toMatch(/missing tenantId/);
  });

  it("non-tenant-scoped kinds still work without tenantId", () => {
    const d = canAccess(
      { role: "platform_admin" },
      "admin:view_schema_proposals",
      { kind: "schema_proposals" },
      opts,
    );
    expect(d.allow).toBe(true);
  });
});

describe("admin:read / internal:proxy actions (Wave 1 tickets A2+A5)", () => {
  const res = { kind: "canonical_memory" as const, tenantId: "t1" };

  it.each<[V1Role, Action, boolean]>([
    ["platform_admin", "admin:read", true],
    ["customer_admin", "admin:read", true],
    ["deployment_strategist", "admin:read", false],
    ["fde", "admin:read", false],
    ["biz_dev", "admin:read", false],
    ["successor_strategist", "admin:read", false],
    ["customer_records_officer", "admin:read", false],
    ["external_auditor", "admin:read", false],
    ["platform_admin", "internal:proxy", true],
    ["customer_admin", "internal:proxy", true],
    ["deployment_strategist", "internal:proxy", true],
    ["fde", "internal:proxy", true],
    ["biz_dev", "internal:proxy", false],
    ["successor_strategist", "internal:proxy", false],
    ["customer_records_officer", "internal:proxy", false],
    ["external_auditor", "internal:proxy", false],
  ])("role %s action %s -> %s", (role, action, expectAllow) => {
    const d = canAccess({ role, tenantId: "t1" }, action, res, opts);
    expect(d.allow).toBe(expectAllow);
  });
});
