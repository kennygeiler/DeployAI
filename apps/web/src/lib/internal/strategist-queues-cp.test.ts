import { afterEach, describe, expect, it, vi } from "vitest";

import { cpListActionQueue } from "@/lib/internal/strategist-queues-cp";

function stubFetchOk() {
  const fetchMock = vi.fn();
  fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve([]) });
  vi.stubGlobal("fetch", fetchMock);
  return fetchMock;
}

describe("cpListActionQueue — engagement scoping", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("scopes the CP request to tenant only when no engagement is given", async () => {
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    const fetchMock = stubFetchOk();

    await cpListActionQueue("tenant-1");

    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("tenant_id=tenant-1");
    expect(url).not.toContain("engagement_id");
  });

  it("appends engagement_id when an engagement is given", async () => {
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    const fetchMock = stubFetchOk();

    await cpListActionQueue("tenant-1", "eng-9");

    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("tenant_id=tenant-1");
    expect(url).toContain("engagement_id=eng-9");
  });
});
