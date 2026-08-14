import type { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpBulkAcceptMock } = vi.hoisted(() => ({
  cpBulkAcceptMock: vi.fn(),
}));

vi.mock("@/lib/internal/matrix-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/matrix-cp")>(
    "@/lib/internal/matrix-cp",
  );
  return {
    ...actual,
    cpBulkAcceptMatrixProposals: cpBulkAcceptMock,
  };
});

import { POST } from "./route";

function authedHeaders(role: string): Headers {
  return new Headers({
    "x-deployai-role": role,
    "x-deployai-tenant": "t1",
    "x-deployai-actor-id": "00000000-0000-7000-8000-0000000000aa",
  });
}

function req(body: unknown): NextRequest {
  return new Request("http://test/api/bff/engagements/eng-42/proposals/accept-bulk", {
    method: "POST",
    body: JSON.stringify(body),
    headers: { "Content-Type": "application/json" },
  }) as unknown as NextRequest;
}

const ctx = { params: Promise.resolve({ engagementId: "eng-42" }) };

describe("POST /api/bff/engagements/[engagementId]/proposals/accept-bulk", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders("deployment_strategist"));
    cookiesMock.mockResolvedValue({ get: () => undefined });
    cpBulkAcceptMock.mockResolvedValue({ accepted: 2, failed: [], skipped: 0 });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpBulkAcceptMock.mockReset();
  });

  it("proxies a filter body to the CP with the server-side actor id", async () => {
    const res = await POST(req({ filter: { status: "pending" } }), ctx);
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({ accepted: 2, failed: [], skipped: 0 });
    expect(cpBulkAcceptMock).toHaveBeenCalledWith("t1", "eng-42", {
      filter: { status: "pending" },
      actor_id: "00000000-0000-7000-8000-0000000000aa",
    });
  });

  it("demo_guest may bulk-accept (the tour's Accept-all beats depend on it)", async () => {
    // canonical:read gate — same accepted-risk posture as the single
    // accept/reject BFF routes; the /api/internal proxy stays denied.
    headersMock.mockResolvedValue(authedHeaders("demo_guest"));
    const res = await POST(req({ filter: { status: "pending" } }), ctx);
    expect(res.status).toBe(200);
    expect(cpBulkAcceptMock).toHaveBeenCalled();
  });

  it("rejects a body carrying both proposal_ids and filter", async () => {
    const res = await POST(
      req({
        proposal_ids: ["11111111-1111-4111-8111-111111111111"],
        filter: { status: "pending" },
      }),
      ctx,
    );
    expect(res.status).toBe(400);
    expect(cpBulkAcceptMock).not.toHaveBeenCalled();
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const res = await POST(req({ filter: { status: "pending" } }), ctx);
    expect(res.status).toBe(401);
    expect(cpBulkAcceptMock).not.toHaveBeenCalled();
  });
});
