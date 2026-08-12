import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpExtractMatrixProposalsMock } = vi.hoisted(() => ({
  cpExtractMatrixProposalsMock: vi.fn(),
}));

vi.mock("@/lib/internal/matrix-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/matrix-cp")>(
    "@/lib/internal/matrix-cp",
  );
  return {
    ...actual,
    cpExtractMatrixProposals: cpExtractMatrixProposalsMock,
  };
});

import { POST } from "./route";

function authedHeaders(role = "fde"): Headers {
  return new Headers({ "x-deployai-role": role, "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ engagementId: "e1" });
}

function req(body: unknown): Request {
  return new Request("http://localhost/api/bff/engagements/e1/extract", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

const proposal = {
  id: "p1",
  engagement_id: "e1",
  source_event_id: "ev1",
  proposal_kind: "node",
  payload: { node_type: "decision", title: "Edge inference" },
  rationale: null,
  status: "pending",
  created_at: "2026-08-11T00:00:00Z",
  decided_at: null,
  decided_by: null,
  result_node_id: null,
  result_edge_id: null,
};

describe("POST /api/bff/engagements/[engagementId]/extract", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpExtractMatrixProposalsMock.mockReset();
  });

  it("runs extraction on the event and returns the proposals", async () => {
    cpExtractMatrixProposalsMock.mockResolvedValue([proposal]);

    const res = await POST(req({ event_id: "ev1" }) as unknown as Parameters<typeof POST>[0], {
      params: params(),
    });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(cpExtractMatrixProposalsMock).toHaveBeenCalledWith("t1", "e1", "ev1", { force: false });
    expect(body.proposals).toHaveLength(1);
    expect(body.proposals[0].id).toBe("p1");
  });

  it("passes force through", async () => {
    cpExtractMatrixProposalsMock.mockResolvedValue([]);

    const res = await POST(
      req({ event_id: "ev1", force: true }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );

    expect(res.status).toBe(200);
    expect(cpExtractMatrixProposalsMock).toHaveBeenCalledWith("t1", "e1", "ev1", { force: true });
  });

  it("400s without an event_id", async () => {
    const res = await POST(req({}) as unknown as Parameters<typeof POST>[0], { params: params() });

    expect(res.status).toBe(400);
    expect(cpExtractMatrixProposalsMock).not.toHaveBeenCalled();
  });

  it("401s when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());

    const res = await POST(req({ event_id: "ev1" }) as unknown as Parameters<typeof POST>[0], {
      params: params(),
    });

    expect(res.status).toBe(401);
    expect(cpExtractMatrixProposalsMock).not.toHaveBeenCalled();
  });

  it("allows demo_guest — capture works on the disposable demo tenant by design", async () => {
    headersMock.mockResolvedValue(authedHeaders("demo_guest"));
    cpExtractMatrixProposalsMock.mockResolvedValue([proposal]);

    const res = await POST(req({ event_id: "ev1" }) as unknown as Parameters<typeof POST>[0], {
      params: params(),
    });

    expect(res.status).toBe(200);
  });
});
