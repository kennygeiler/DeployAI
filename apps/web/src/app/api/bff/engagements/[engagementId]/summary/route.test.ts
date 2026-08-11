import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpGetEngagementSummaryMock } = vi.hoisted(() => ({
  cpGetEngagementSummaryMock: vi.fn(),
}));

vi.mock("@/lib/internal/engagement-summary-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/engagement-summary-cp")>(
    "@/lib/internal/engagement-summary-cp",
  );
  return {
    ...actual,
    cpGetEngagementSummary: cpGetEngagementSummaryMock,
  };
});

import { SummaryEndpointUnavailableError } from "@/lib/internal/engagement-summary-cp";

import { GET } from "./route";

function authedHeaders(): Headers {
  return new Headers({ "x-deployai-role": "fde", "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ engagementId: "e1" });
}

const summary = {
  engagement: {
    id: "e1",
    name: "Eng",
    customer_account: null,
    current_phase: "P1_pre_engagement",
    status: "active",
    updated_at: "2026-08-10T00:00:00Z",
  },
  members: [{ user_id: "u1", display_name: "Ada", email: "a@b.co", role: "fde" }],
  counts: {
    stakeholders: 1,
    decisions: 0,
    risks_open: 0,
    commitments: 0,
    proposals_pending: 0,
    escalations_open: 0,
    disputes_open: 0,
  },
  recent_changes: [],
};

describe("GET /api/bff/engagements/[engagementId]/summary", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpGetEngagementSummaryMock.mockReset();
  });

  it("proxies the CP summary for the actor's tenant", async () => {
    cpGetEngagementSummaryMock.mockResolvedValue(summary);
    const req = new Request("http://localhost/api/bff/engagements/e1/summary");

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(cpGetEngagementSummaryMock).toHaveBeenCalledWith("t1", "e1");
    expect(body.engagement.id).toBe("e1");
    expect(body.counts.stakeholders).toBe(1);
  });

  it("returns 404 when the CP endpoint is not deployed (degrade signal)", async () => {
    cpGetEngagementSummaryMock.mockRejectedValue(new SummaryEndpointUnavailableError());
    const req = new Request("http://localhost/api/bff/engagements/e1/summary");

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });

    expect(res.status).toBe(404);
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const req = new Request("http://localhost/api/bff/engagements/e1/summary");

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });

    expect(res.status).toBe(401);
    expect(cpGetEngagementSummaryMock).not.toHaveBeenCalled();
  });
});
