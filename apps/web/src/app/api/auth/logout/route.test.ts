import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

const fetchMock = vi.fn();

const TENANT = "11111111-1111-1111-1111-111111111111";

function logoutRequest(cookie?: string): Request {
  const headers = new Headers();
  if (cookie) {
    headers.set("cookie", cookie);
  }
  return new Request("https://app.example.com/api/auth/logout", { method: "POST", headers });
}

describe("POST /api/auth/logout", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_OIDC_REDIRECT_URI", "https://app.example.com/api/auth/callback/oidc");
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("revokes the CP refresh session and clears cookies", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));
    const res = await POST(
      logoutRequest(
        `deployai_access_token=jwt; deployai_refresh_token=jti-1; deployai_session_tenant=${TENANT}`,
      ),
    );

    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("https://app.example.com/login");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe("http://cp.test/auth/logout");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toEqual({
      tenant_id: TENANT,
      refresh_token: "jti-1",
    });

    for (const name of [
      "deployai_access_token",
      "deployai_refresh_token",
      "deployai_session_tenant",
    ]) {
      const c = res.cookies.get(name);
      expect(c?.value).toBe("");
      expect(c?.maxAge).toBe(0);
    }
  });

  it("still clears cookies when the CP is unreachable", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const res = await POST(
      logoutRequest(
        `deployai_access_token=jwt; deployai_refresh_token=jti-1; deployai_session_tenant=${TENANT}`,
      ),
    );
    expect(res.status).toBe(303);
    expect(res.cookies.get("deployai_access_token")?.value).toBe("");
  });

  it("skips revocation when there is no refresh cookie", async () => {
    const res = await POST(logoutRequest());
    expect(res.status).toBe(303);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("supports GET for plain-link logout", async () => {
    const res = await GET(logoutRequest());
    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("https://app.example.com/login");
  });
});
