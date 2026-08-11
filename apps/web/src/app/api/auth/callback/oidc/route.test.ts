import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const fetchMock = vi.fn();

function stubOidcEnv(): void {
  vi.stubEnv("DEPLOYAI_OIDC_ISSUER", "https://idp.example.com/realms/deployai");
  vi.stubEnv("DEPLOYAI_OIDC_CLIENT_ID", "deployai-web");
  vi.stubEnv("DEPLOYAI_OIDC_REDIRECT_URI", "https://app.example.com/api/auth/callback/oidc");
  vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
}

function callbackRequest(opts?: { query?: string; cookie?: string | null }): Request {
  const query = opts?.query ?? "code=abc&state=s1";
  const cookie =
    opts?.cookie === undefined
      ? "dep_oidc_state=s1; dep_oidc_verifier=v1; dep_oidc_nonce=n1"
      : opts.cookie;
  const headers = new Headers();
  if (cookie) {
    headers.set("cookie", cookie);
  }
  return new Request(`https://app.example.com/api/auth/callback/oidc?${query}`, { headers });
}

function cpSessionJson(): Response {
  return new Response(
    JSON.stringify({
      sub: "entra|sub-1",
      user_id: "22222222-2222-2222-2222-222222222222",
      tenant_id: "11111111-1111-1111-1111-111111111111",
      access_token: "cp-access-jwt",
      refresh_token: "refresh-jti-1",
      token_type: "Bearer",
      expires_in: 900,
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

describe("GET /api/auth/callback/oidc", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    stubOidcEnv();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("returns 503 oidc-not-configured when issuer env is unset", async () => {
    vi.stubEnv("DEPLOYAI_OIDC_ISSUER", "");
    const res = await GET(callbackRequest());
    expect(res.status).toBe(503);
    expect(await res.text()).toBe("oidc-not-configured");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 400 when code or state is missing", async () => {
    const res = await GET(callbackRequest({ query: "state=s1" }));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 400 on state mismatch with the login cookie", async () => {
    const res = await GET(
      callbackRequest({ cookie: "dep_oidc_state=OTHER; dep_oidc_verifier=v1; dep_oidc_nonce=n1" }),
    );
    expect(res.status).toBe(400);
    expect(await res.text()).toContain("oidc-state-mismatch");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("returns 400 when the transient cookies are missing entirely", async () => {
    const res = await GET(callbackRequest({ cookie: null }));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("happy path: forwards cookies to CP, sets session cookies, redirects to app", async () => {
    fetchMock.mockResolvedValue(cpSessionJson());
    const res = await GET(callbackRequest());

    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("https://app.example.com/engagements");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [cpUrl, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
    expect(String(cpUrl)).toBe("http://cp.test/auth/oidc/callback?code=abc&state=s1");
    const sentCookie = new Headers(init.headers).get("cookie");
    expect(sentCookie).toContain("dep_oidc_state=s1");
    expect(sentCookie).toContain("dep_oidc_verifier=v1");
    expect(sentCookie).toContain("dep_oidc_nonce=n1");

    expect(res.cookies.get("deployai_access_token")?.value).toBe("cp-access-jwt");
    expect(res.cookies.get("deployai_refresh_token")?.value).toBe("refresh-jti-1");
    expect(res.cookies.get("deployai_session_tenant")?.value).toBe(
      "11111111-1111-1111-1111-111111111111",
    );
    const access = res.cookies.get("deployai_access_token");
    expect(access?.httpOnly).toBe(true);
    expect(access?.sameSite).toBe("lax");
    expect(access?.path).toBe("/");
    expect(access?.secure).toBe(true); // redirect URI is https
    // Transient login cookies are cleared.
    expect(res.cookies.get("dep_oidc_state")?.value).toBe("");
    expect(res.cookies.get("dep_oidc_verifier")?.value).toBe("");
    expect(res.cookies.get("dep_oidc_nonce")?.value).toBe("");
  });

  it("maps CP 400 (bad code / bad ID-token signature) to 400", async () => {
    fetchMock.mockResolvedValue(new Response('{"detail":"invalid id_token"}', { status: 400 }));
    const res = await GET(callbackRequest());
    expect(res.status).toBe(400);
    expect(await res.text()).toBe("oidc-token-verification-failed");
    expect(res.cookies.get("deployai_access_token")).toBeUndefined();
  });

  it("maps CP 403 (unknown user, JIT disabled) to 403", async () => {
    fetchMock.mockResolvedValue(
      new Response('{"detail":"Unknown user and JIT provisioning is disabled"}', { status: 403 }),
    );
    const res = await GET(callbackRequest());
    expect(res.status).toBe(403);
    expect(await res.text()).toContain("oidc-user-not-provisioned");
    expect(res.cookies.get("deployai_access_token")).toBeUndefined();
  });

  it("redirects to /login?error=issuer_unreachable when CP reports 502", async () => {
    fetchMock.mockResolvedValue(
      new Response('{"detail":"metadata fetch failed"}', { status: 502 }),
    );
    const res = await GET(callbackRequest());
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://app.example.com/login?error=issuer_unreachable",
    );
  });

  it("redirects to /login?error=control_plane_unreachable when the CP fetch throws", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const res = await GET(callbackRequest());
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://app.example.com/login?error=control_plane_unreachable",
    );
  });

  it("redirects to /login?error=idp_error when the IdP returns an error param", async () => {
    const res = await GET(callbackRequest({ query: "error=access_denied&state=s1" }));
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe("https://app.example.com/login?error=idp_error");
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
