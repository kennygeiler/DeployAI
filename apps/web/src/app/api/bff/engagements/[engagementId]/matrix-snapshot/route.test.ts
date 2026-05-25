import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const { headersMock, cookiesMock } = vi.hoisted(() => ({
  headersMock: vi.fn(),
  cookiesMock: vi.fn(),
}));

vi.mock("next/headers", () => ({
  headers: () => headersMock(),
  cookies: () => cookiesMock(),
}));

const { cpGetMatrixSnapshotMock } = vi.hoisted(() => ({
  cpGetMatrixSnapshotMock: vi.fn(),
}));

vi.mock("@/lib/internal/matrix-snapshot-cp", async () => {
  const actual = await vi.importActual<typeof import("@/lib/internal/matrix-snapshot-cp")>(
    "@/lib/internal/matrix-snapshot-cp",
  );
  return {
    ...actual,
    cpGetMatrixSnapshot: cpGetMatrixSnapshotMock,
  };
});

import { GET } from "./route";

function authedHeaders(): Headers {
  return new Headers({ "x-deployai-role": "fde", "x-deployai-tenant": "t1" });
}

function params() {
  return Promise.resolve({ engagementId: "e1" });
}

const snapshot = {
  captured_at: "2026-05-20T00:00:00Z",
  nodes: [{ id: "n1" }],
  edges: [{ id: "ed1" }],
};

function makeReq(at: string | null): Parameters<typeof GET>[0] {
  const url =
    at == null
      ? "http://localhost/api/bff/engagements/e1/matrix-snapshot"
      : `http://localhost/api/bff/engagements/e1/matrix-snapshot?at=${encodeURIComponent(at)}`;
  return new Request(url) as unknown as Parameters<typeof GET>[0];
}

describe("GET /api/bff/engagements/[engagementId]/matrix-snapshot", () => {
  beforeEach(() => {
    headersMock.mockResolvedValue(authedHeaders());
    cookiesMock.mockResolvedValue({ get: () => undefined });
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    cpGetMatrixSnapshotMock.mockReset();
  });

  it("forwards valid at to the CP client and returns the snapshot", async () => {
    cpGetMatrixSnapshotMock.mockResolvedValue(snapshot);

    const res = await GET(makeReq("2026-05-20"), { params: params() });

    expect(res.status).toBe(200);
    expect(cpGetMatrixSnapshotMock).toHaveBeenCalledWith("t1", "e1", "2026-05-20");
    const body = await res.json();
    expect(body.snapshot).toEqual(snapshot);
    expect(body.source).toBe("cp");
  });

  it("returns 422 when at is missing", async () => {
    const res = await GET(makeReq(null), { params: params() });

    expect(res.status).toBe(422);
    expect(cpGetMatrixSnapshotMock).not.toHaveBeenCalled();
  });

  it("returns 422 when at is malformed", async () => {
    const res = await GET(makeReq("2026/05/20"), { params: params() });

    expect(res.status).toBe(422);
    expect(cpGetMatrixSnapshotMock).not.toHaveBeenCalled();
  });

  it("returns 422 for a non-YYYY-MM-DD shape (e.g. timestamp)", async () => {
    const res = await GET(makeReq("2026-05-20T00:00:00Z"), { params: params() });

    expect(res.status).toBe(422);
    expect(cpGetMatrixSnapshotMock).not.toHaveBeenCalled();
  });

  it("propagates 404 from CP when no snapshot exists at/before that date", async () => {
    cpGetMatrixSnapshotMock.mockRejectedValue(new Error("cp matrix-snapshot get 404: not found"));

    const res = await GET(makeReq("2026-05-20"), { params: params() });

    expect(res.status).toBe(404);
    const body = await res.json();
    expect(body.code).toBe("cp_not_found");
  });

  it("returns 401 when no actor", async () => {
    headersMock.mockResolvedValue(new Headers());

    const res = await GET(makeReq("2026-05-20"), { params: params() });

    expect(res.status).toBe(401);
    expect(cpGetMatrixSnapshotMock).not.toHaveBeenCalled();
  });
});
