import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpFetchChainMock } = vi.hoisted(() => ({
  cpFetchChainMock: vi.fn(),
}));

vi.mock("@/lib/internal/ledger-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/ledger-cp")>(
    "@/lib/internal/ledger-cp",
  );
  return {
    ...actual,
    cpFetchChain: cpFetchChainMock,
  };
});

import { GET } from "./route";

function authedHeaders(): Headers {
  return new Headers({ "x-deployai-role": "fde", "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ engagementId: "e1", eventId: "ev1" });
}

const sampleChain = {
  rootEventId: "ev1",
  nodes: [
    {
      id: "ev1",
      occurredAt: "2026-05-20T10:00:00Z",
      sourceKind: "matrix_node_created",
      summary: "Decision node created",
      actorKind: "user",
      depth: 0,
      truncated: false,
    },
    {
      id: "ev2",
      occurredAt: "2026-05-19T10:00:00Z",
      sourceKind: "email_ingest",
      summary: "Customer email landed",
      actorKind: "system",
      depth: 1,
      truncated: false,
    },
  ],
  edges: [{ fromEventId: "ev2", toEventId: "ev1" }],
  truncatedAtDepth: null,
  truncatedNodeCount: null,
};

describe("GET /api/bff/engagements/[engagementId]/ledger/chain/[eventId]", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpFetchChainMock.mockReset();
  });

  it("forwards params and returns the chain", async () => {
    cpFetchChainMock.mockResolvedValue(sampleChain);
    const req = new Request(
      "http://localhost/api/bff/engagements/e1/ledger/chain/ev1?max_depth=5&direction=backward",
    );
    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(200);
    expect(cpFetchChainMock).toHaveBeenCalledWith("t1", "e1", "ev1", {
      max_depth: 5,
      direction: "backward",
    });
    const body = await res.json();
    expect(body.rootEventId).toBe("ev1");
    expect(body.nodes.length).toBe(2);
    expect(body.source).toBe("cp");
  });

  it("uses default max_depth when omitted", async () => {
    cpFetchChainMock.mockResolvedValue(sampleChain);
    const req = new Request("http://localhost/api/bff/engagements/e1/ledger/chain/ev1");
    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(200);
    expect(cpFetchChainMock).toHaveBeenCalledWith("t1", "e1", "ev1", { max_depth: 3 });
  });

  it("rejects an out-of-range max_depth", async () => {
    const req = new Request(
      "http://localhost/api/bff/engagements/e1/ledger/chain/ev1?max_depth=99",
    );
    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(400);
    expect(cpFetchChainMock).not.toHaveBeenCalled();
  });

  it("returns 422 when CP returns a node with an unknown source_kind", async () => {
    cpFetchChainMock.mockResolvedValue({
      ...sampleChain,
      nodes: [
        ...sampleChain.nodes,
        {
          id: "ev3",
          occurredAt: "2026-05-18T10:00:00Z",
          sourceKind: "totally_bogus_kind",
          summary: "Should be rejected",
          actorKind: "system",
          depth: 2,
          truncated: false,
        },
      ],
    });
    const req = new Request("http://localhost/api/bff/engagements/e1/ledger/chain/ev1");
    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(422);
    const body = await res.json();
    expect(body.error).toContain("totally_bogus_kind");
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const req = new Request("http://localhost/api/bff/engagements/e1/ledger/chain/ev1");
    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(401);
    expect(cpFetchChainMock).not.toHaveBeenCalled();
  });
});
