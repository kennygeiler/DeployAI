import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpIngestInteractionMock, cpExtractMatrixProposalsMock } = vi.hoisted(() => ({
  cpIngestInteractionMock: vi.fn(),
  cpExtractMatrixProposalsMock: vi.fn(),
}));

vi.mock("@/lib/internal/ingest-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/ingest-cp")>(
    "@/lib/internal/ingest-cp",
  );
  return {
    ...actual,
    cpIngestInteraction: cpIngestInteractionMock,
  };
});

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
  return new Request("http://localhost/api/bff/engagements/e1/ingest", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
}

const event = { id: "ev1", engagement_id: "e1", event_type: "ingest.email" };

describe("POST /api/bff/engagements/[engagementId]/ingest", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    cpIngestInteractionMock.mockResolvedValue(event);
    cpExtractMatrixProposalsMock.mockResolvedValue([]);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpIngestInteractionMock.mockReset();
    cpExtractMatrixProposalsMock.mockReset();
  });

  it("ingests and chains extraction by default", async () => {
    const res = await POST(
      req({ source: "email", content: { text: "hi" } }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body.event.id).toBe("ev1");
    expect(cpExtractMatrixProposalsMock).toHaveBeenCalledWith("t1", "e1", "ev1");
  });

  it("skips chained extraction when extract:false (K2 staged flow)", async () => {
    const res = await POST(
      req({
        source: "email",
        content: { text: "hi" },
        extract: false,
      }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body.event.id).toBe("ev1");
    expect(body.extract_error).toBeNull();
    expect(cpExtractMatrixProposalsMock).not.toHaveBeenCalled();
  });

  it("still 201s the ingest when chained extraction fails (best-effort)", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    cpExtractMatrixProposalsMock.mockRejectedValue(new Error("llm down"));

    const res = await POST(
      req({ source: "email", content: { text: "hi" } }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );
    const body = await res.json();

    expect(res.status).toBe(201);
    expect(body.extract_error).toContain("llm down");
  });

  it("allows demo_guest — capture works on the disposable demo tenant by design", async () => {
    headersMock.mockResolvedValue(authedHeaders("demo_guest"));

    const res = await POST(
      req({ source: "email", content: { text: "hi" } }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );

    expect(res.status).toBe(201);
  });

  it("401s when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());

    const res = await POST(
      req({ source: "email", content: { text: "hi" } }) as unknown as Parameters<typeof POST>[0],
      { params: params() },
    );

    expect(res.status).toBe(401);
    expect(cpIngestInteractionMock).not.toHaveBeenCalled();
  });
});
