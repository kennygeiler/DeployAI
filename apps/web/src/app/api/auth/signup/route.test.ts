import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

const fetchMock = vi.fn();

function req(body: unknown): Request {
  return new Request("https://app.example.com/api/auth/signup", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

const GOOD_BODY = {
  email: "founder@acme.example",
  password: "a strong enough passphrase",
  workspace_name: "Acme",
  display_name: "Founder",
};

function cpSessionJson(): Response {
  return new Response(
    JSON.stringify({
      user_id: "22222222-2222-2222-2222-222222222222",
      tenant_id: "11111111-1111-1111-1111-111111111111",
      access_token: "cp-access-jwt",
      refresh_token: "cp-refresh-jti",
      expires_in: 900,
      roles: ["customer_admin"],
    }),
    { status: 201, headers: { "Content-Type": "application/json" } },
  );
}

beforeEach(() => {
  vi.unstubAllEnvs();
  vi.stubEnv("NEXT_PUBLIC_SELF_SERVE_SIGNUP", "1");
  vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("POST /api/auth/signup", () => {
  it("404s when NEXT_PUBLIC_SELF_SERVE_SIGNUP is not 1 (route effectively absent)", async () => {
    vi.stubEnv("NEXT_PUBLIC_SELF_SERVE_SIGNUP", "");
    const res = await POST(req(GOOD_BODY));
    expect(res.status).toBe(404);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("mirrors a CP 404 (CP-side gate off)", async () => {
    fetchMock.mockResolvedValue(new Response("nope", { status: 404 }));
    const res = await POST(req(GOOD_BODY));
    expect(res.status).toBe(404);
  });

  it("happy path: provisions via CP and sets session cookies", async () => {
    fetchMock.mockResolvedValue(cpSessionJson());
    const res = await POST(req(GOOD_BODY));
    expect(res.status).toBe(201);
    expect((await res.json()).ok).toBe(true);
    const [cpUrl] = fetchMock.mock.calls[0] as [string];
    expect(String(cpUrl)).toBe("http://cp.test/api/v1/auth/signup");
    expect(res.cookies.get("deployai_access_token")?.value).toBe("cp-access-jwt");
    expect(res.cookies.get("deployai_session_tenant")?.value).toBe(
      "11111111-1111-1111-1111-111111111111",
    );
  });

  it("forwards CP policy rejections (422)", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "Password must be at least 10 characters." }), {
        status: 422,
      }),
    );
    const res = await POST(req({ ...GOOD_BODY, password: "short" }));
    expect(res.status).toBe(422);
    expect((await res.json()).error).toMatch(/at least 10/);
  });

  it("forwards CP duplicate-email conflicts (409)", async () => {
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "An account with this email already exists." }), {
        status: 409,
      }),
    );
    const res = await POST(req(GOOD_BODY));
    expect(res.status).toBe(409);
  });

  it("400s on missing fields without calling the CP", async () => {
    const res = await POST(req({ email: "a@b.co", password: "some password 1" }));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
