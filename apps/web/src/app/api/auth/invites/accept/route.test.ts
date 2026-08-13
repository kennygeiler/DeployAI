import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST } from "./route";

const fetchMock = vi.fn();

function req(body: unknown): Request {
  return new Request("https://app.example.com/api/auth/invites/accept", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
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

describe("POST /api/auth/invites/accept", () => {
  it("accepts and lands the invitee signed in (cookies set)", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          user_id: "44444444-4444-4444-4444-444444444444",
          tenant_id: "11111111-1111-1111-1111-111111111111",
          access_token: "invitee-jwt",
          refresh_token: "invitee-refresh",
          expires_in: 900,
          roles: ["deployment_strategist"],
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
    const res = await POST(
      req({ token: "raw-token-abc", password: "teammate passphrase 9", display_name: "T" }),
    );
    expect(res.status).toBe(201);
    expect((await res.json()).ok).toBe(true);
    const [cpUrl] = fetchMock.mock.calls[0] as [string];
    expect(String(cpUrl)).toBe("http://cp.test/api/v1/auth/invites/accept");
    expect(res.cookies.get("deployai_access_token")?.value).toBe("invitee-jwt");
    expect(res.cookies.get("deployai_session_tenant")?.value).toBe(
      "11111111-1111-1111-1111-111111111111",
    );
  });

  it("forwards the generic dead-token 404", async () => {
    fetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({ detail: "This invite link is invalid, expired, or already used." }),
        { status: 404 },
      ),
    );
    const res = await POST(
      req({ token: "dead", password: "teammate passphrase 9", display_name: "T" }),
    );
    expect(res.status).toBe(404);
  });

  it("400s on missing fields without calling the CP", async () => {
    const res = await POST(req({ token: "raw-token-abc" }));
    expect(res.status).toBe(400);
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
