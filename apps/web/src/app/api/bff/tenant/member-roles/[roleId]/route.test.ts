import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpUpdateMemberRoleMock, cpDeleteMemberRoleMock } = vi.hoisted(() => ({
  cpUpdateMemberRoleMock: vi.fn(),
  cpDeleteMemberRoleMock: vi.fn(),
}));

vi.mock("@/lib/internal/member-roles-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/member-roles-cp")>(
    "@/lib/internal/member-roles-cp",
  );
  return {
    ...actual,
    cpUpdateMemberRole: cpUpdateMemberRoleMock,
    cpDeleteMemberRole: cpDeleteMemberRoleMock,
  };
});

import { PUT } from "./route";

function authedHeaders(): Headers {
  return new Headers({ "x-deployai-role": "fde", "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ roleId: "mr-1" });
}

describe("PUT /api/bff/tenant/member-roles/[roleId]", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpUpdateMemberRoleMock.mockReset();
    cpDeleteMemberRoleMock.mockReset();
  });

  it("returns 400 on empty body", async () => {
    const req = new Request("http://localhost/api/bff/tenant/member-roles/mr-1", {
      method: "PUT",
    });
    const res = await PUT(req, { params: params() });
    expect(res?.status).toBe(400);
    expect(cpUpdateMemberRoleMock).not.toHaveBeenCalled();
  });

  it("returns 400 on malformed JSON", async () => {
    const req = new Request("http://localhost/api/bff/tenant/member-roles/mr-1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: "not json",
    });
    const res = await PUT(req, { params: params() });
    expect(res?.status).toBe(400);
    expect(cpUpdateMemberRoleMock).not.toHaveBeenCalled();
  });

  it("returns 400 when label is empty", async () => {
    const req = new Request("http://localhost/api/bff/tenant/member-roles/mr-1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: "   " }),
    });
    const res = await PUT(req, { params: params() });
    expect(res?.status).toBe(400);
    expect(cpUpdateMemberRoleMock).not.toHaveBeenCalled();
  });

  it("trims label before dispatching to CP", async () => {
    cpUpdateMemberRoleMock.mockResolvedValue({
      id: "mr-1",
      name: "x",
      label: "Renamed",
      description: null,
    });
    const req = new Request("http://localhost/api/bff/tenant/member-roles/mr-1", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ label: "  Renamed  " }),
    });
    const res = await PUT(req, { params: params() });
    expect(res?.status).toBe(200);
    expect(cpUpdateMemberRoleMock).toHaveBeenCalledWith("t1", "mr-1", { label: "Renamed" });
  });
});
