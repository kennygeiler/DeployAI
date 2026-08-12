/**
 * Wave 1 ticket A2 — middleware hardening tests:
 *  - matcher covers /admin and /api/internal (previously bypassed entirely)
 *  - inbound strategist header stripping applies on those paths
 *  - dev role injection is strictly opt-in (and double-gated on production builds)
 *  - tenant header is required by default (opt-out is DEPLOYAI_STRATEGIST_REQUIRE_TENANT=0)
 *  - per-surface actions: admin:read for /admin, internal:proxy for /api/internal
 */
import { NextRequest } from "next/server";
import { afterEach, describe, expect, it, vi } from "vitest";

import { config, middleware } from "../middleware";

const T_A = "11111111-1111-1111-1111-111111111111";
const T_B = "22222222-2222-2222-2222-222222222222";

function req(path: string, headers: Record<string, string> = {}): NextRequest {
  return new NextRequest(`http://localhost${path}`, { headers });
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("middleware matcher (ticket A2)", () => {
  it("covers /admin and /api/internal in addition to strategist surfaces", () => {
    expect(config.matcher).toEqual(
      expect.arrayContaining([
        "/admin",
        "/admin/:path*",
        "/api/internal/:path*",
        "/api/bff/:path*",
      ]),
    );
  });
});

describe("admin surface gating (admin:read)", () => {
  it("denies deployment_strategist on /admin pages", async () => {
    const res = await middleware(
      req("/admin/agent-kenny-dashboard", {
        "x-deployai-role": "deployment_strategist",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(403);
  });

  it("allows platform_admin on /admin pages", async () => {
    const res = await middleware(
      req("/admin/agent-kenny-dashboard", {
        "x-deployai-role": "platform_admin",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(200);
  });

  it("allows customer_admin on /admin pages", async () => {
    const res = await middleware(
      req("/admin", { "x-deployai-role": "customer_admin", "x-deployai-tenant": T_A }),
    );
    expect(res.status).toBe(200);
  });

  it("rejects requests without a role on /admin (previously unprotected)", async () => {
    const res = await middleware(req("/admin/agent-kenny-dashboard"));
    expect(res.status).toBe(403);
  });
});

describe("internal API gating (internal:proxy)", () => {
  it("denies biz_dev on /api/internal routes", async () => {
    const res = await middleware(
      req(`/api/internal/v1/tenants/${T_A}/mcp_configs`, {
        "x-deployai-role": "biz_dev",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(403);
  });

  it("allows deployment_strategist on their own tenant's internal routes", async () => {
    const res = await middleware(
      req(`/api/internal/v1/tenants/${T_A}/mcp_configs`, {
        "x-deployai-role": "deployment_strategist",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(200);
  });

  it("blocks cross-tenant access: actor tenant differs from the path tenant", async () => {
    const res = await middleware(
      req(`/api/internal/v1/tenants/${T_B}/mcp_configs`, {
        "x-deployai-role": "deployment_strategist",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(403);
  });

  it("platform_admin may cross tenants on internal routes", async () => {
    const res = await middleware(
      req(`/api/internal/v1/tenants/${T_B}/mcp_configs`, {
        "x-deployai-role": "platform_admin",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(200);
  });

  it("rejects requests without a role on /api/internal (previously unprotected)", async () => {
    const res = await middleware(req(`/api/internal/v1/tenants/${T_A}/mcp_killswitch`));
    expect(res.status).toBe(403);
  });
});

describe("demo_guest role (Wave 4S guest demo access)", () => {
  it("is accepted on strategist read surfaces (canonical:read)", async () => {
    const res = await middleware(
      req("/engagements", { "x-deployai-role": "demo_guest", "x-deployai-tenant": T_A }),
    );
    expect(res.status).toBe(200);
  });

  it("is accepted on /api/bff routes (read + Oracle chat surfaces)", async () => {
    const res = await middleware(
      req("/api/bff/engagements", { "x-deployai-role": "demo_guest", "x-deployai-tenant": T_A }),
    );
    expect(res.status).toBe(200);
  });

  it("is denied on /admin pages (no admin:read)", async () => {
    const res = await middleware(
      req("/admin/agent-kenny-dashboard", {
        "x-deployai-role": "demo_guest",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(403);
  });

  it("is denied on /api/internal/v1 proxy routes (no internal:proxy — bulk accept, MCP config)", async () => {
    const res = await middleware(
      req(`/api/internal/v1/tenants/${T_A}/mcp_configs`, {
        "x-deployai-role": "demo_guest",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(403);
  });

  it("cannot reach another tenant's internal routes either", async () => {
    const res = await middleware(
      req(`/api/internal/v1/tenants/${T_B}/mcp_configs`, {
        "x-deployai-role": "demo_guest",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(403);
  });
});

describe("inbound strategist header stripping runs on newly matched paths", () => {
  function activateStripPolicy() {
    vi.stubEnv("DEPLOYAI_WEB_CLEAR_STRATEGIST_HEADERS_BEFORE_JWT", "1");
    vi.stubEnv("DEPLOYAI_WEB_TRUST_JWT", "1");
    vi.stubEnv(
      "DEPLOYAI_WEB_JWT_PUBLIC_KEY_PEM",
      "-----BEGIN PUBLIC KEY-----\nfake\n-----END PUBLIC KEY-----",
    );
  }

  it("forged role headers on /api/internal are stripped, so the request is rejected", async () => {
    activateStripPolicy();
    const res = await middleware(
      req(`/api/internal/v1/tenants/${T_A}/mcp_configs`, {
        "x-deployai-role": "platform_admin",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(403);
  });

  it("forged role headers on /admin are stripped, so the request is rejected", async () => {
    activateStripPolicy();
    const res = await middleware(
      req("/admin/agent-kenny-dashboard", {
        "x-deployai-role": "platform_admin",
        "x-deployai-tenant": T_A,
      }),
    );
    expect(res.status).toBe(403);
  });
});

describe("tenant requirement defaults ON (opt-out is =0)", () => {
  it("rejects a valid role without a tenant header", async () => {
    const res = await middleware(
      req("/engagements", { "x-deployai-role": "deployment_strategist" }),
    );
    expect(res.status).toBe(403);
    expect(await res.text()).toMatch(/x-deployai-tenant/);
  });

  it("applies on /api/bff too", async () => {
    const res = await middleware(req("/api/bff/engagements", { "x-deployai-role": "fde" }));
    expect(res.status).toBe(403);
    expect(await res.text()).toMatch(/x-deployai-tenant/);
  });

  it("allows the request when the tenant header is present", async () => {
    const res = await middleware(
      req("/engagements", { "x-deployai-role": "deployment_strategist", "x-deployai-tenant": T_A }),
    );
    expect(res.status).toBe(200);
  });

  it("opt-out (=0) skips the tenant-presence check but still fails closed in authz", async () => {
    vi.stubEnv("DEPLOYAI_STRATEGIST_REQUIRE_TENANT", "0");
    const res = await middleware(
      req("/engagements", { "x-deployai-role": "deployment_strategist" }),
    );
    // No tenant can be derived → canAccess policy error → deny, never allow.
    expect(res.status).toBe(403);
  });
});

describe("dev role injection is strictly opt-in (ticket A2)", () => {
  it("does not inject when DEPLOYAI_LOCAL_DEV_ROLE_INJECT is unset", async () => {
    const res = await middleware(req("/engagements"));
    expect(res.status).toBe(403);
  });

  it("injects when DEPLOYAI_LOCAL_DEV_ROLE_INJECT=1 on a non-production build", async () => {
    vi.stubEnv("DEPLOYAI_LOCAL_DEV_ROLE_INJECT", "1");
    const res = await middleware(req("/engagements"));
    expect(res.status).toBe(200);
  });

  it("refuses to inject on a production build without the second override", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("DEPLOYAI_LOCAL_DEV_ROLE_INJECT", "1");
    const res = await middleware(req("/engagements"));
    expect(res.status).toBe(403);
  });

  it("injects on a production build only with DEPLOYAI_DEV_ROLE_INJECT_ALLOW_PRODUCTION=1", async () => {
    vi.stubEnv("NODE_ENV", "production");
    vi.stubEnv("DEPLOYAI_LOCAL_DEV_ROLE_INJECT", "1");
    vi.stubEnv("DEPLOYAI_DEV_ROLE_INJECT_ALLOW_PRODUCTION", "1");
    const res = await middleware(req("/engagements"));
    expect(res.status).toBe(200);
  });

  it("DEPLOYAI_DISABLE_DEV_STRATEGIST=1 is an unconditional kill switch", async () => {
    vi.stubEnv("DEPLOYAI_LOCAL_DEV_ROLE_INJECT", "1");
    vi.stubEnv("DEPLOYAI_DISABLE_DEV_STRATEGIST", "1");
    const res = await middleware(req("/engagements"));
    expect(res.status).toBe(403);
  });

  it("injected dev role honors DEPLOYAI_DEV_STRATEGIST_ROLE for any valid role", async () => {
    vi.stubEnv("DEPLOYAI_LOCAL_DEV_ROLE_INJECT", "1");
    vi.stubEnv("DEPLOYAI_DEV_STRATEGIST_ROLE", "platform_admin");
    const res = await middleware(req("/admin/agent-kenny-dashboard"));
    expect(res.status).toBe(200);
  });
});

describe("unauthenticated browser redirect (bootstrap login)", () => {
  it("redirects HTML page requests without a role to /login?next=", async () => {
    const res = await middleware(
      req("/engagements", { accept: "text/html,application/xhtml+xml" }),
    );
    expect(res.status).toBe(307);
    const loc = new URL(res.headers.get("location") ?? "", "http://localhost");
    expect(loc.pathname).toBe("/login");
    expect(loc.searchParams.get("next")).toBe("/engagements");
  });

  it("keeps the machine-readable 403 for API and non-HTML requests", async () => {
    const api = await middleware(req("/api/bff/engagements", { accept: "application/json" }));
    expect(api.status).toBe(403);
    const noAccept = await middleware(req("/engagements"));
    expect(noAccept.status).toBe(403);
  });
});
