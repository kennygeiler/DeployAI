import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpListEvalRunsMock } = vi.hoisted(() => ({
  cpListEvalRunsMock: vi.fn(),
}));

vi.mock("@/lib/internal/eval-runs-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/eval-runs-cp")>(
    "@/lib/internal/eval-runs-cp",
  );
  return {
    ...actual,
    cpListEvalRuns: cpListEvalRunsMock,
  };
});

import { GET } from "./route";

function authedHeaders(role = "fde"): Headers {
  return new Headers({ "x-deployai-role": role, "x-deployai-tenant": "t1" });
}

const sampleRun = {
  id: "run-1",
  run_at: "2026-08-11T10:00:00Z",
  source: "ci",
  runtime: "langgraph",
  question_count: 30,
  pass_rate: 0.9,
  idk_rate: 0.2,
  hallucination_rate: 0.03,
  cross_engagement_leak_count: 0,
  p50_ms: 1200,
  p95_ms: 4100,
};

describe("GET /api/bff/admin/eval-runs", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpListEvalRunsMock.mockReset();
  });

  it("forwards the limit to CP and returns the runs", async () => {
    cpListEvalRunsMock.mockResolvedValue([sampleRun]);
    const res = await GET(new Request("http://localhost/api/bff/admin/eval-runs?limit=25"));

    expect(res.status).toBe(200);
    expect(cpListEvalRunsMock).toHaveBeenCalledWith({ limit: 25 });
    const body = await res.json();
    expect(body.runs).toEqual([sampleRun]);
  });

  it("omits limit when not supplied", async () => {
    cpListEvalRunsMock.mockResolvedValue([]);
    const res = await GET(new Request("http://localhost/api/bff/admin/eval-runs"));
    expect(res.status).toBe(200);
    expect(cpListEvalRunsMock).toHaveBeenCalledWith({ limit: undefined });
  });

  it("rejects an out-of-range limit before touching CP", async () => {
    const res = await GET(new Request("http://localhost/api/bff/admin/eval-runs?limit=9999"));
    expect(res.status).toBe(400);
    expect(cpListEvalRunsMock).not.toHaveBeenCalled();
  });

  it("returns 401 without an actor", async () => {
    headersMock.mockResolvedValue(new Headers());
    const res = await GET(new Request("http://localhost/api/bff/admin/eval-runs"));
    expect(res.status).toBe(401);
    expect(cpListEvalRunsMock).not.toHaveBeenCalled();
  });

  it("returns 403 for a role without internal:proxy", async () => {
    headersMock.mockResolvedValue(authedHeaders("biz_dev"));
    const res = await GET(new Request("http://localhost/api/bff/admin/eval-runs"));
    expect(res.status).toBe(403);
    expect(cpListEvalRunsMock).not.toHaveBeenCalled();
  });

  it("maps a CP failure through the standard BFF error shape", async () => {
    cpListEvalRunsMock.mockRejectedValue(new Error("cp eval-runs list 500: boom"));
    const res = await GET(new Request("http://localhost/api/bff/admin/eval-runs"));
    expect(res.status).toBe(502);
    const body = await res.json();
    expect(body.source).toBe("cp_error");
  });
});
