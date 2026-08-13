import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpListEngagementsMock } = vi.hoisted(() => ({
  cpListEngagementsMock: vi.fn(),
}));

vi.mock("@/lib/internal/engagements-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/engagements-cp")>(
    "@/lib/internal/engagements-cp",
  );
  return {
    ...actual,
    cpListEngagements: cpListEngagementsMock,
  };
});

import { GET } from "./route";

const SANDBOX_ID = "55555555-5555-4555-8555-555555555555";

function authedHeaders(role: string): Headers {
  return new Headers({ "x-deployai-role": role, "x-deployai-tenant": "t1" });
}

function withCookie(value: string | undefined) {
  cookiesMock.mockResolvedValue({
    get: (name: string) =>
      name === "demo_engagement" && value !== undefined ? { name, value } : undefined,
  });
}

describe("GET /api/bff/engagements (guest-sandbox list hygiene)", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders("fde"));
    withCookie(undefined);
    cpListEngagementsMock.mockResolvedValue([]);
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpListEngagementsMock.mockReset();
  });

  it("non-demo roles list without any sandbox filter (unchanged behavior)", async () => {
    const res = await GET();
    expect(res.status).toBe(200);
    expect(cpListEngagementsMock).toHaveBeenCalledWith("t1", undefined);
  });

  it("demo_guest with a sandbox cookie sees fixtures + its own sandbox only", async () => {
    headersMock.mockResolvedValue(authedHeaders("demo_guest"));
    withCookie(SANDBOX_ID);
    const res = await GET();
    expect(res.status).toBe(200);
    expect(cpListEngagementsMock).toHaveBeenCalledWith("t1", {
      excludeDemoSandboxes: true,
      visibleSandboxId: SANDBOX_ID,
    });
  });

  it("demo_guest without the cookie degrades to fixtures only (no sandbox id)", async () => {
    headersMock.mockResolvedValue(authedHeaders("demo_guest"));
    const res = await GET();
    expect(res.status).toBe(200);
    expect(cpListEngagementsMock).toHaveBeenCalledWith("t1", {
      excludeDemoSandboxes: true,
      visibleSandboxId: null,
    });
  });

  it("demo_guest with a mangled cookie is treated as cookie-less, not an error", async () => {
    headersMock.mockResolvedValue(authedHeaders("demo_guest"));
    withCookie("not-a-uuid; DROP TABLE engagements");
    const res = await GET();
    expect(res.status).toBe(200);
    expect(cpListEngagementsMock).toHaveBeenCalledWith("t1", {
      excludeDemoSandboxes: true,
      visibleSandboxId: null,
    });
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const res = await GET();
    expect(res.status).toBe(401);
    expect(cpListEngagementsMock).not.toHaveBeenCalled();
  });
});
