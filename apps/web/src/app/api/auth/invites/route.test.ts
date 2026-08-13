import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

const fetchMock = vi.fn();

function postReq(body: unknown, withCookie = true): Request {
  return new Request("https://app.example.com/api/auth/invites", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(withCookie ? { cookie: "deployai_access_token=admin-jwt" } : {}),
    },
    body: JSON.stringify(body),
  });
}

beforeEach(() => {
  vi.unstubAllEnvs();
  vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/auth/invites", () => {
  it("401s without a session cookie", async () => {
    const res = await POST(postReq({ email: "x@y.co", role: "fde" }, false));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("builds an absolute join_url from the request origin", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          invite_id: "33333333-3333-3333-3333-333333333333",
          email: "x@y.co",
          role: "deployment_strategist",
          expires_at: "2026-08-20T00:00:00Z",
          join_path: "/join/raw-token-abc",
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    const res = await POST(postReq({ email: "x@y.co", role: "deployment_strategist" }));
    expect(res.status).toBe(201);
    const body = await res.json();
    expect(body.join_url).toBe("https://app.example.com/join/raw-token-abc");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer admin-jwt");
  });

  it("forwards the CP's admin-role rejection (403)", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "customer_admin role required" }), { status: 403 }),
    );
    const res = await POST(postReq({ email: "x@y.co", role: "fde" }));
    expect(res.status).toBe(403);
  });
});

describe("GET /api/auth/invites", () => {
  it("returns the CP's pending list", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify([
          {
            invite_id: "33333333-3333-3333-3333-333333333333",
            email: "x@y.co",
            role: "fde",
            expires_at: "2026-08-20T00:00:00Z",
            created_at: "2026-08-13T00:00:00Z",
          },
        ]),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const res = await GET(
      new Request("https://app.example.com/api/auth/invites", {
        headers: { cookie: "deployai_access_token=admin-jwt" },
      }),
    );
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body).toHaveLength(1);
    expect(body[0].email).toBe("x@y.co");
  });
});
