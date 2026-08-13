import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

const fetchMock = vi.fn();

function req(body: unknown, withCookie = true): Request {
  return new Request("https://app.example.com/api/auth/change-password", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(withCookie ? { cookie: "deployai_access_token=session-jwt" } : {}),
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

describe("POST /api/auth/change-password", () => {
  it("401s without a session cookie", async () => {
    const res = await POST(req({ current_password: "a", new_password: "b" }, false));
    expect(res.status).toBe(401);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards the cookie JWT as a bearer and swaps in the reminted session", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          user_id: "22222222-2222-2222-2222-222222222222",
          tenant_id: "11111111-1111-1111-1111-111111111111",
          access_token: "new-access-jwt",
          refresh_token: "new-refresh-jti",
          expires_in: 900,
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      ),
    );
    const res = await POST(
      req({ current_password: "old password 1", new_password: "new password 2" }),
    );
    expect(res.status).toBe(200);
    const [cpUrl, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(cpUrl)).toBe("http://cp.test/api/v1/auth/password");
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer session-jwt");
    // The CP revoked every refresh session; this browser keeps the new pair.
    expect(res.cookies.get("deployai_access_token")?.value).toBe("new-access-jwt");
    expect(res.cookies.get("deployai_refresh_token")?.value).toBe("new-refresh-jti");
  });

  it("forwards a wrong-current-password 401 from the CP", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "current password is incorrect" }), { status: 401 }),
    );
    const res = await POST(
      req({ current_password: "wrong password", new_password: "new password 2" }),
    );
    expect(res.status).toBe(401);
    expect((await res.json()).error).toBe("current password is incorrect");
  });
});
