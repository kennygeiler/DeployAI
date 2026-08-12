import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";
import { demoRateLimited, resetDemoRateLimiter } from "@/lib/internal/demo-rate-limit";

const fetchMock = vi.fn();

function stubDemoEnv(): void {
  vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "1");
  vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
  vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "int-key-1");
}

function demoRequest(ip = "203.0.113.7"): Request {
  return new Request("https://app.example.com/api/auth/demo", {
    headers: { "x-forwarded-for": ip },
  });
}

function cpDemoSessionJson(): Response {
  return new Response(
    JSON.stringify({
      access_token: "demo-access-jwt",
      refresh_token: "demo-refresh-jti",
      token_type: "Bearer",
      expires_in: 900,
      tenant_id: "33333333-3333-3333-3333-333333333333",
      roles: ["demo_guest"],
    }),
    { status: 201, headers: { "Content-Type": "application/json" } },
  );
}

describe("GET /api/auth/demo", () => {
  beforeEach(() => {
    vi.unstubAllEnvs();
    stubDemoEnv();
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    resetDemoRateLimiter();
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("404s when NEXT_PUBLIC_DEMO_MODE is not 1 (route effectively absent)", async () => {
    vi.stubEnv("NEXT_PUBLIC_DEMO_MODE", "");
    const res = await GET(demoRequest());
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("503s when the control plane base/key is not configured", async () => {
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "");
    const res = await GET(demoRequest());
    expect(res.status).toBe(503);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("happy path: mints via CP with the internal key, sets cookies, redirects to /engagements", async () => {
    fetchMock.mockResolvedValue(cpDemoSessionJson());
    const res = await GET(demoRequest());

    expect(res.status).toBe(303);
    expect(res.headers.get("location")).toBe("https://app.example.com/engagements");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [cpUrl, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(cpUrl)).toBe("http://cp.test/internal/v1/demo/session");
    expect(init.method).toBe("POST");
    expect(new Headers(init.headers).get("X-DeployAI-Internal-Key")).toBe("int-key-1");

    const access = res.cookies.get("deployai_access_token");
    expect(access?.value).toBe("demo-access-jwt");
    expect(access?.httpOnly).toBe(true);
    expect(access?.sameSite).toBe("lax");
    expect(access?.path).toBe("/");
    expect(access?.secure).toBe(true); // request is https
    expect(access?.maxAge).toBe(900);
    expect(res.cookies.get("deployai_session_tenant")?.value).toBe(
      "33333333-3333-3333-3333-333333333333",
    );
    // No refresh cookie: demo sessions just expire.
    expect(res.cookies.get("deployai_refresh_token")).toBeUndefined();
  });

  it("mirrors CP 404 (demo disabled on the CP) as 404", async () => {
    fetchMock.mockResolvedValue(new Response('{"detail":"disabled"}', { status: 404 }));
    const res = await GET(demoRequest());
    expect(res.status).toBe(404);
    expect(res.cookies.get("deployai_access_token")).toBeUndefined();
  });

  it("redirects to /login?error=demo_unavailable when the CP errors", async () => {
    fetchMock.mockResolvedValue(new Response("boom", { status: 500 }));
    const res = await GET(demoRequest());
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://app.example.com/login?error=demo_unavailable",
    );
  });

  it("redirects to /login?error=demo_unavailable when the CP fetch throws", async () => {
    fetchMock.mockRejectedValue(new TypeError("fetch failed"));
    const res = await GET(demoRequest());
    expect(res.status).toBe(302);
    expect(res.headers.get("location")).toBe(
      "https://app.example.com/login?error=demo_unavailable",
    );
  });

  it("429s after the per-IP budget is exhausted (naive single-instance limiter)", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(cpDemoSessionJson()));
    for (let i = 0; i < 10; i++) {
      const ok = await GET(demoRequest("198.51.100.9"));
      expect(ok.status).toBe(303);
    }
    const limited = await GET(demoRequest("198.51.100.9"));
    expect(limited.status).toBe(429);
    // A different IP is unaffected.
    const other = await GET(demoRequest("198.51.100.10"));
    expect(other.status).toBe(303);
  });
});

describe("demoRateLimited window behavior", () => {
  beforeEach(() => resetDemoRateLimiter());

  it("resets the budget after the window elapses", () => {
    const t0 = 1_000_000;
    for (let i = 0; i < 10; i++) {
      expect(demoRateLimited("ip-a", t0 + i)).toBe(false);
    }
    expect(demoRateLimited("ip-a", t0 + 11)).toBe(true);
    expect(demoRateLimited("ip-a", t0 + 60_001)).toBe(false);
  });
});
