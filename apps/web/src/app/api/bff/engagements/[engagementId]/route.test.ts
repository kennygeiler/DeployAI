import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpGetEngagementDetailMock } = vi.hoisted(() => ({
  cpGetEngagementDetailMock: vi.fn(),
}));

vi.mock("@/lib/internal/engagements-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/engagements-cp")>(
    "@/lib/internal/engagements-cp",
  );
  return {
    ...actual,
    cpGetEngagementDetail: cpGetEngagementDetailMock,
  };
});

import { GET } from "./route";

function authedHeaders(): Headers {
  return new Headers({ "x-deployai-role": "fde", "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ engagementId: "e1" });
}

const aggregate = {
  engagement: { id: "e1", tenant_id: "t1", name: "Eng", current_phase: "P1_pre_engagement" },
  members: [{ id: "m1" }],
  matrix_nodes: [{ id: "n1" }],
  matrix_edges: [{ id: "ed1" }],
  matrix_proposals: [{ id: "p1" }],
  custom_node_types: [{ name: "custom", label: "Custom", color: "#000000" }],
  insights: [{ id: "i1" }],
  recent_activity_events: [
    { id: "a1", occurred_at: "2026-05-25T00:00:00Z", event_type: "x", source_ref: null },
  ],
};

describe("GET /api/bff/engagements/[engagementId]", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpGetEngagementDetailMock.mockReset();
  });

  it("fans in a single CP aggregate call (cuts the prior 6 round-trips to 1)", async () => {
    cpGetEngagementDetailMock.mockResolvedValue(aggregate);
    const req = new Request("http://localhost/api/bff/engagements/e1");

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });

    expect(res.status).toBe(200);
    expect(cpGetEngagementDetailMock).toHaveBeenCalledTimes(1);
    expect(cpGetEngagementDetailMock).toHaveBeenCalledWith("t1", "e1");
  });

  it("maps the aggregate into the page's existing response shape", async () => {
    cpGetEngagementDetailMock.mockResolvedValue(aggregate);
    const req = new Request("http://localhost/api/bff/engagements/e1");

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    const body = await res.json();

    expect(body.engagement.id).toBe("e1");
    expect(body.members).toEqual(aggregate.members);
    expect(body.matrix.nodes).toEqual(aggregate.matrix_nodes);
    expect(body.matrix.edges).toEqual(aggregate.matrix_edges);
    expect(body.matrix.proposals).toEqual(aggregate.matrix_proposals);
    expect(body.matrix.node_types).toEqual(aggregate.custom_node_types);
    expect(body.source).toBe("cp");
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const req = new Request("http://localhost/api/bff/engagements/e1");

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });

    expect(res.status).toBe(401);
    expect(cpGetEngagementDetailMock).not.toHaveBeenCalled();
  });
});
