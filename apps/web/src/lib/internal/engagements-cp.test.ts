import { afterEach, describe, expect, it, vi } from "vitest";

import { cpGetEngagementDetail, cpListEngagements } from "@/lib/internal/engagements-cp";

function stubFetchOk(body: unknown = []) {
  const fetchMock = vi.fn();
  fetchMock.mockResolvedValue({ ok: true, json: () => Promise.resolve(body) });
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

describe("cpGetEngagementDetail", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
  });

  it("issues exactly one CP request to the aggregate endpoint", async () => {
    vi.stubEnv("DEPLOYAI_CONTROL_PLANE_URL", "http://cp.test");
    vi.stubEnv("DEPLOYAI_INTERNAL_API_KEY", "k");
    const fetchMock = stubFetchOk({
      engagement: { id: "e1" },
      members: [],
      matrix_nodes: [],
      matrix_edges: [],
      matrix_proposals: [],
      custom_node_types: [],
      insights: [],
      recent_activity_events: [],
    });

    const detail = await cpGetEngagementDetail("tenant-1", "engagement-1");

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("/internal/v1/engagements/engagement-1/detail");
    expect(url).toContain("tenant_id=tenant-1");
    expect(detail.engagement).toEqual({ id: "e1" });
  });
});
