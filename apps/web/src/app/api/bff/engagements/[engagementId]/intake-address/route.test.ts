import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpGetIntakeAddressMock } = vi.hoisted(() => ({
  cpGetIntakeAddressMock: vi.fn(),
}));

vi.mock("@/lib/internal/intake-address-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/intake-address-cp")>(
    "@/lib/internal/intake-address-cp",
  );
  return { ...actual, cpGetIntakeAddress: cpGetIntakeAddressMock };
});

import { GET } from "./route";

function authedHeaders(role = "fde"): Headers {
  return new Headers({ "x-deployai-role": role, "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ engagementId: "e1" });
}

function req(): Request {
  return new Request("http://localhost/api/bff/engagements/e1/intake-address");
}

const address = {
  local_part: "acme-abc",
  email: "acme-abc@intake.example.com",
  created_at: "2026-08-13T00:00:00Z",
};

describe("GET /api/bff/engagements/[engagementId]/intake-address", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    cpGetIntakeAddressMock.mockResolvedValue(address);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpGetIntakeAddressMock.mockReset();
  });

  it("returns the address with can_regenerate=false for a strategist-tier role", async () => {
    const res = await GET(req() as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ ...address, can_regenerate: false });
    expect(cpGetIntakeAddressMock).toHaveBeenCalledWith("t1", "e1");
  });

  it("flags can_regenerate=true for customer_admin", async () => {
    headersMock.mockResolvedValue(authedHeaders("customer_admin"));
    const res = await GET(req() as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(200);
    expect((await res.json()).can_regenerate).toBe(true);
  });

  it("401s without an actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const res = await GET(req() as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(401);
    expect(cpGetIntakeAddressMock).not.toHaveBeenCalled();
  });

  it("maps a CP failure through the shared error envelope", async () => {
    cpGetIntakeAddressMock.mockRejectedValue(new Error("cp intake-address 500: boom"));
    const res = await GET(req() as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(502);
    expect((await res.json()).source).toBe("cp_error");
  });
});
