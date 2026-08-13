import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

const fetchMock = vi.fn();

function req(body: unknown): Request {
  return new Request("https://app.example.com/api/auth/signin", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

function cpSessionJson(): Response {
  return new Response(
    JSON.stringify({
      user_id: "22222222-2222-2222-2222-222222222222",
      tenant_id: "11111111-1111-1111-1111-111111111111",
      access_token: "cp-access-jwt",
      refresh_token: "cp-refresh-jti",
      token_type: "Bearer",
      expires_in: 900,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
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

describe("POST /api/auth/signin", () => {
  it("503s when the control plane is not configured", async () => {
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "");
    const res = await POST(req({ email: "a@b.co", password: "x" }));
    expect(res.status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("400s on missing fields without calling the CP", async () => {
    const res = await POST(req({ email: "a@b.co" }));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("happy path: calls CP login and sets the three session cookies", async () => {
    fetchMock.mockResolvedValue(cpSessionJson());
    const res = await POST(req({ email: "a@b.co", password: "some password 1" }));
    expect(res.status).toBe(200);
    expect((await res.json()).ok).toBe(true);

    const [cpUrl, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(cpUrl)).toBe("http://cp.test/api/v1/auth/login");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({ email: "a@b.co", password: "some password 1" });

    const access = res.cookies.get("deployai_access_token");
    expect(access?.value).toBe("cp-access-jwt");
    expect(access?.httpOnly).toBe(true);
    expect(access?.sameSite).toBe("lax");
    expect(access?.secure).toBe(true); // https request
    expect(res.cookies.get("deployai_refresh_token")?.value).toBe("cp-refresh-jti");
    expect(res.cookies.get("deployai_session_tenant")?.value).toBe(
      "11111111-1111-1111-1111-111111111111",
    );
  });

  it("forwards the CP's uniform 401 detail without cookies", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "invalid email or password" }), { status: 401 }),
    );
    const res = await POST(req({ email: "a@b.co", password: "wrong password" }));
    expect(res.status).toBe(401);
    expect((await res.json()).error).toBe("invalid email or password");
    expect(res.cookies.get("deployai_access_token")).toBeUndefined();
  });

  it("forwards a CP 429 (attempt limiter)", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "too many attempts; try again later" }), {
        status: 429,
      }),
    );
    const res = await POST(req({ email: "a@b.co", password: "wrong password" }));
    expect(res.status).toBe(429);
  });

  it("502s when the CP is unreachable", async () => {
    fetchMock.mockRejectedValue(new Error("boom"));
    const res = await POST(req({ email: "a@b.co", password: "x-password-1" }));
    expect(res.status).toBe(502);
  });
});
