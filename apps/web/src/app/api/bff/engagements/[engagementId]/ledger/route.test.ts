import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpListLedgerMock } = vi.hoisted(() => ({
  cpListLedgerMock: vi.fn(),
}));

vi.mock("@/lib/internal/ledger-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/ledger-cp")>(
    "@/lib/internal/ledger-cp",
  );
  return {
    ...actual,
    cpListLedger: cpListLedgerMock,
  };
});

import { GET } from "./route";

function authedHeaders(): Headers {
  return new Headers({ "x-deployai-role": "fde", "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ engagementId: "e1" });
}

const sampleList = {
  events: [
    {
      id: "ev1",
      engagement_id: "e1",
      occurred_at: "2026-05-20T10:00:00Z",
      recorded_at: "2026-05-20T10:00:01Z",
      actor_kind: "user",
      actor_id: "u1",
      source_kind: "email_ingest",
      source_ref: null,
      summary: "Email landed",
      detail: {},
      caused_by_ids: [],
      affects: [],
    },
  ],
  next_cursor: null,
};

describe("GET /api/bff/engagements/[engagementId]/ledger", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpListLedgerMock.mockReset();
  });

  it("forwards query params to CP and returns the list", async () => {
    cpListLedgerMock.mockResolvedValue(sampleList);
    const req = new Request(
      "http://localhost/api/bff/engagements/e1/ledger?source_kind=email_ingest,meeting_webhook&limit=50&from=2026-05-01T00:00:00Z",
    );

    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });

    expect(res.status).toBe(200);
    expect(cpListLedgerMock).toHaveBeenCalledWith("t1", "e1", {
      limit: 50,
      from: "2026-05-01T00:00:00Z",
      source_kind: ["email_ingest", "meeting_webhook"],
    });
    const body = await res.json();
    expect(body.events.length).toBe(1);
    expect(body.source).toBe("cp");
  });

  it("rejects an out-of-range limit", async () => {
    const req = new Request("http://localhost/api/bff/engagements/e1/ledger?limit=9999");
    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(400);
    expect(cpListLedgerMock).not.toHaveBeenCalled();
  });

  it("rejects an invalid from timestamp", async () => {
    const req = new Request("http://localhost/api/bff/engagements/e1/ledger?from=not-a-date");
    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(400);
    expect(cpListLedgerMock).not.toHaveBeenCalled();
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const req = new Request("http://localhost/api/bff/engagements/e1/ledger");
    const res = await GET(req as unknown as Parameters<typeof GET>[0], { params: params() });
    expect(res.status).toBe(401);
    expect(cpListLedgerMock).not.toHaveBeenCalled();
  });
});
