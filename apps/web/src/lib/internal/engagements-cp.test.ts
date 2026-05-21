import { afterEach, describe, expect, it, vi } from "vitest";

import { cpListEngagements } from "@/lib/internal/engagements-cp";

function stubFetchOk() {
  const fetchMock = vi.fn();
  fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("cpListEngagements", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("requests the tenant-scoped engagements endpoint", async () => {
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    const fetchMock = stubFetchOk();

    await cpListEngagements("tenant-1");

    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("/internal/v1/engagements");
    expect(url).toContain("tenant_id=tenant-1");
  });
});
