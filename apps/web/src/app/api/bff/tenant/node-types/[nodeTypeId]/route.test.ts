import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpUpdateNodeTypeMock, cpDeleteNodeTypeMock } = vi.hoisted(() => ({
  cpUpdateNodeTypeMock: vi.fn(),
  cpDeleteNodeTypeMock: vi.fn(),
}));

vi.mock("@/lib/internal/node-types-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/node-types-cp")>(
    "@/lib/internal/node-types-cp",
  );
  return {
    ...actual,
    cpUpdateNodeType: cpUpdateNodeTypeMock,
    cpDeleteNodeType: cpDeleteNodeTypeMock,
  };
});

import { PUT } from "./route";

function authedHeaders(): Headers {
  return new Headers({ "x-deployai-role": "fde", "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ nodeTypeId: "nt-1" });
}

describe("PUT /api/bff/tenant/node-types/[nodeTypeId]", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpUpdateNodeTypeMock.mockReset();
    cpDeleteNodeTypeMock.mockReset();
  });

  it("returns 400 on empty body", async () => {
    const req = new Request("http://localhost/api/bff/tenant/node-types/nt-1", {
      method: "PUT",
    });
    const res = await PUT(req, { params: params() });
    expect(res?.status).toBe(400);
    expect(cpUpdateNodeTypeMock).not.toHaveBeenCalled();
  });

  it("returns 400 on malformed JSON", async () => {
    const req = new Request("http://localhost/api/bff/tenant/node-types/nt-1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: "not json",
    });
    const res = await PUT(req, { params: params() });
    expect(res?.status).toBe(400);
    expect(cpUpdateNodeTypeMock).not.toHaveBeenCalled();
  });

  it("returns 400 when label is empty", async () => {
    const req = new Request("http://localhost/api/bff/tenant/node-types/nt-1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: "   " }),
    });
    const res = await PUT(req, { params: params() });
    expect(res?.status).toBe(400);
    expect(cpUpdateNodeTypeMock).not.toHaveBeenCalled();
  });

  it("trims label before dispatching to CP", async () => {
    cpUpdateNodeTypeMock.mockResolvedValue({
      id: "nt-1",
      name: "x",
      label: "Renamed",
      color: null,
      description: null,
    });
    const req = new Request("http://localhost/api/bff/tenant/node-types/nt-1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: "  Renamed  " }),
    });
    const res = await PUT(req, { params: params() });
    expect(res?.status).toBe(200);
    expect(cpUpdateNodeTypeMock).toHaveBeenCalledWith("t1", "nt-1", { label: "Renamed" });
  });
});
