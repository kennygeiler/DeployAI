import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpDismissGapAskMock } = vi.hoisted(() => ({
  cpDismissGapAskMock: vi.fn(),
}));

vi.mock("@/lib/internal/gap-asks-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/gap-asks-cp")>(
    "@/lib/internal/gap-asks-cp",
  );
  return {
    ...actual,
    cpDismissGapAsk: cpDismissGapAskMock,
  };
});

import { POST } from "./route";

function authedHeaders(): Headers {
  return new Headers({
    "x-deployai-role": "fde",
    "x-deployai-tenant": "t1",
    "x-deployai-actor-id": "u1",
  });
}

function params() {
  return Promise.resolve({ engagementId: "e1", askId: "a1b2c3d4e5f60718" });
}

describe("POST /api/bff/engagements/[engagementId]/gap-asks/[askId]/dismiss", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpDismissGapAskMock.mockReset();
  });

  it("dismisses through the CP with the actor id", async () => {
    cpDismissGapAskMock.mockResolvedValue({
      ask_id: "a1b2c3d4e5f60718",
      dismissed_at: "2026-08-13T00:00:00Z",
      snooze_until: null,
    });
    const req = new Request(
      "http://localhost/api/bff/engagements/e1/gap-asks/a1b2c3d4e5f60718/dismiss",
      { method: "POST", body: "{}" },
    );

    const res = await POST(req as unknown as Parameters<typeof POST>[0], { params: params() });
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(cpDismissGapAskMock).toHaveBeenCalledWith("t1", "e1", "a1b2c3d4e5f60718", {
      dismissedBy: "u1",
    });
    expect(body.dismissal.ask_id).toBe("a1b2c3d4e5f60718");
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const req = new Request(
      "http://localhost/api/bff/engagements/e1/gap-asks/a1b2c3d4e5f60718/dismiss",
      { method: "POST", body: "{}" },
    );

    const res = await POST(req as unknown as Parameters<typeof POST>[0], { params: params() });

    expect(res.status).toBe(401);
    expect(cpDismissGapAskMock).not.toHaveBeenCalled();
  });
});
