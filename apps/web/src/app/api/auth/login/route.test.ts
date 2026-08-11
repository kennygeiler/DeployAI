import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

const fetchMock = vi.fn();

function stubOidcEnv(): void {
  vi.stubEnv("DEPLOYAI_OIDC_ISSUER", "https://idp.example.com/realms/deployai");
  vi.stubEnv("DEPLOYAI_OIDC_CLIENT_ID", "deployai-web");
  vi.stubEnv("DEPLOYAI_OIDC_REDIRECT_URI", "https://app.example.com/api/auth/callback/oidc");
}

function metadataJson(): Response {
  return new Response(
    JSON.stringify({
      issuer: "https://idp.example.com/realms/deployai",
      authorization_endpoint: "https://idp.example.com/realms/deployai/authorize",
      token_endpoint: "https://idp.example.com/realms/deployai/token",
      jwks_uri: "https://idp.example.com/realms/deployai/jwks",
    }),
    { status: 200, headers: { "Content-Type": "application/json" } },
  );
}

describe("GET /api/auth/login", () => {
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

  it("returns 503 when OIDC env is not configured", async () => {
    vi.stubEnv("DEPLOYAI_OIDC_CLIENT_ID", "");
    const res = await GET(new Request("https://app.example.com/api/auth/login"));
    expect(res.status).toBe(503);
    expect(await res.text()).toBe("oidc-not-configured");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("redirects to the issuer authorize endpoint with PKCE + state + nonce cookies", async () => {
    fetchMock.mockResolvedValue(metadataJson());
    const res = await GET(new Request("https://app.example.com/api/auth/login"));

    expect(res.status).toBe(302);
    const loc = res.headers.get("location");
    expect(loc).toBeTruthy();
    const u = new URL(loc!);
    expect(`${u.origin}${u.pathname}`).toBe("https://idp.example.com/realms/deployai/authorize");
    expect(u.searchParams.get("client_id")).toBe("deployai-web");
    expect(u.searchParams.get("response_type")).toBe("code");
    expect(u.searchParams.get("redirect_uri")).toBe(
      "https://app.example.com/api/auth/callback/oidc",
    );
    expect(u.searchParams.get("code_challenge_method")).toBe("S256");
    expect(u.searchParams.get("scope")).toContain("openid");

    const state = res.cookies.get("dep_oidc_state");
    const verifier = res.cookies.get("dep_oidc_verifier");
    const nonce = res.cookies.get("dep_oidc_nonce");
    expect(state?.value).toBe(u.searchParams.get("state"));
    expect(nonce?.value).toBe(u.searchParams.get("nonce"));
    expect(verifier?.value).toBeTruthy();
    // The challenge is derived from the verifier, never the verifier itself.
    expect(u.searchParams.get("code_challenge")).not.toBe(verifier?.value);
    for (const c of [state, verifier, nonce]) {
      expect(c?.httpOnly).toBe(true);
      expect(c?.sameSite).toBe("lax");
      expect(c?.path).toBe("/");
      expect(c?.secure).toBe(true);
    }
  });

  it("redirects to /login?error=issuer_unreachable when metadata fetch fails", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const res = await GET(new Request("https://app.example.com/api/auth/login"));
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://app.example.com/login?error=issuer_unreachable",
    );
  });

  it("redirects to /login?error=issuer_unreachable on non-2xx metadata response", async () => {
    fetchMock.mockResolvedValue(new Response("nope", { status: 500 }));
    const res = await GET(new Request("https://app.example.com/api/auth/login"));
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://app.example.com/login?error=issuer_unreachable",
    );
  });
});
