import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpRegenerateIntakeAddressMock } = vi.hoisted(() => ({
  cpRegenerateIntakeAddressMock: vi.fn(),
}));

vi.mock("@/lib/internal/intake-address-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/intake-address-cp")>(
    "@/lib/internal/intake-address-cp",
  );
  return { ...actual, cpRegenerateIntakeAddress: cpRegenerateIntakeAddressMock };
});

import { POST } from "./route";

function authedHeaders(role: string, actorId?: string): Headers {
  const h = new Headers({ "x-deployai-role": role, "x-deployai-tenant": "t1" });
  if (actorId) {
    h.set("x-deployai-actor-id", actorId);
  }
  return h;
}

function params() {
  return Promise.resolve({ engagementId: "e1" });
}

function req(): Request {
  return new Request("http://localhost/api/bff/engagements/e1/intake-address/regenerate", {
    method: "POST",
  });
}

const address = {
  local_part: "acme-new",
  email: "acme-new@intake.example.com",
  created_at: "2026-08-13T00:00:00Z",
};

describe("POST /api/bff/engagements/[engagementId]/intake-address/regenerate", () => {
  beforeEach(() => {
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    cpRegenerateIntakeAddressMock.mockResolvedValue(address);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpRegenerateIntakeAddressMock.mockReset();
  });

  it.each(["customer_admin", "platform_admin"])("regenerates for %s", async (role) => {
    headersMock.mockResolvedValue(authedHeaders(role, "admin-1"));
    const res = await POST(req() as unknown as Parameters<typeof POST>[0], { params: params() });
    expect(res.status).toBe(201);
    expect(await res.json()).toEqual({ ...address, can_regenerate: true });
    expect(cpRegenerateIntakeAddressMock).toHaveBeenCalledWith("t1", "e1", "admin-1");
  });

  it.each(["fde", "deployment_strategist", "demo_guest", "biz_dev"])(
    "403s for non-admin role %s",
    async (role) => {
      headersMock.mockResolvedValue(authedHeaders(role));
      const res = await POST(req() as unknown as Parameters<typeof POST>[0], { params: params() });
      expect(res.status).toBe(403);
      expect(cpRegenerateIntakeAddressMock).not.toHaveBeenCalled();
    },
  );

  it("401s without an actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const res = await POST(req() as unknown as Parameters<typeof POST>[0], { params: params() });
    expect(res.status).toBe(401);
  });

  it("maps a CP failure through the shared error envelope", async () => {
    headersMock.mockResolvedValue(authedHeaders("customer_admin"));
    cpRegenerateIntakeAddressMock.mockRejectedValue(
      new Error("cp intake-address regenerate 500: boom"),
    );
    const res = await POST(req() as unknown as Parameters<typeof POST>[0], { params: params() });
    expect(res.status).toBe(502);
  });
});
