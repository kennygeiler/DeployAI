import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpGetGapAsksMock } = vi.hoisted(() => ({
  cpGetGapAsksMock: vi.fn(),
}));

vi.mock("@/lib/internal/gap-asks-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/gap-asks-cp")>(
    "@/lib/internal/gap-asks-cp",
  );
  return {
    ...actual,
    cpGetGapAsks: cpGetGapAsksMock,
  };
});

import { GapAsksEndpointUnavailableError } from "@/lib/internal/gap-asks-cp";

import { GET } from "./route";

function authedHeaders(): Headers {
  return new Headers({ "x-deployai-role": "fde", "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ engagementId: "e1" });
}

const asks = [
  {
    id: "a1b2c3d4e5f60718",
    rule: "risk_unmitigated",
    severity: "high",
    target_node_id: "n1",
    title: "What is being done about “Calibration slip”?",
    why: "Risk “Calibration slip” is open with no mitigation on record.",
    remedy_kind: "answer",
  },
];

describe("GET /api/bff/engagements/[engagementId]/gap-asks", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpGetGapAsksMock.mockReset();
  });

  it("proxies the CP asks for the actor's tenant", async () => {
    cpGetGapAsksMock.mockResolvedValue(asks);
    const req = new Request("http://localhost/api/bff/engagements/e1/gap-asks");

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(cpGetGapAsksMock).toHaveBeenCalledWith("t1", "e1");
    expect(body.asks).toHaveLength(1);
    expect(body.asks[0].rule).toBe("risk_unmitigated");
  });

  it("returns 404 when the CP endpoint is not deployed (quiet degrade)", async () => {
    cpGetGapAsksMock.mockRejectedValue(new GapAsksEndpointUnavailableError());
    const req = new Request("http://localhost/api/bff/engagements/e1/gap-asks");

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });

    expect(res.status).toBe(404);
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const req = new Request("http://localhost/api/bff/engagements/e1/gap-asks");

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });

    expect(res.status).toBe(401);
    expect(cpGetGapAsksMock).not.toHaveBeenCalled();
  });
});
