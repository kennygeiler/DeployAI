import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MatrixInsight } from "@/lib/bff/matrix-types";

import { EngagementInsights } from "./EngagementInsights.client";

function mkInsight(overrides: Partial<MatrixInsight> = {}): MatrixInsight {
  return {
    id: "i1",
    tenant_id: "t1",
    engagement_id: "e1",
    agent: "oracle",
    insight_type: "stale_commitment",
    severity: "high",
    title: "Pilot ship date is slipping",
    body: "Commitment cited 35 days ago. Confirm a new date with the sponsor by EOD.",
    citation_node_ids: ["n1"],
    citation_edge_ids: [],
    citation_event_ids: ["ev1"],
    dedup_key: "oracle:e1:stale_commitment:n1",
    status: "open",
    created_at: "2026-05-09T00:00:00Z",
    decided_at: null,
    decided_by: null,
    ...overrides,
  };
}

function mockFetch(handlers: Record<string, () => unknown>) {
  const calls: Array<{ url: string; method: string }> = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string }) => {
    const method = init?.method ?? "GET";
    calls.push({ url, method });
    for (const [pattern, handler] of Object.entries(handlers)) {
      if (url.includes(pattern)) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(handler()) });
      }
    }
    return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("EngagementInsights", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the empty state when the BFF returns no insights", async () => {
    mockFetch({
      "/insights": () => ({ insights: [] }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText(/No insights yet/)).toBeTruthy();
  });

  it("renders a populated list with severity badge + body", async () => {
    mockFetch({
      "/insights": () => ({ insights: [mkInsight()] }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("Pilot ship date is slipping")).toBeTruthy());
    expect(screen.getByLabelText("severity high")).toBeTruthy();
    expect(screen.getByText(/Confirm a new date/)).toBeTruthy();
    // insight_type renders human-readable
    expect(screen.getByText(/stale commitment/i)).toBeTruthy();
  });

  it("refresh button calls the refresh endpoint and replaces the list", async () => {
    const calls = mockFetch({
      "/insights/refresh": () => ({ insights: [mkInsight({ title: "After refresh" })] }),
      "/insights": () => ({ insights: [mkInsight({ title: "Before refresh" })] }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("Before refresh")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /refresh insights/i }));

    await waitFor(() => expect(screen.getByText("After refresh")).toBeTruthy());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toContain("/api/bff/engagements/e1/insights/refresh");
  });

  it("dismiss button POSTs and re-fetches the list", async () => {
    let listCallCount = 0;
    const calls = mockFetch({
      "/insights/i1/dismiss": () => ({ insight: { ...mkInsight(), status: "dismissed" } }),
      "/insights": () => {
        listCallCount += 1;
        // First call (mount): one insight. Second call (after dismiss): none.
        return { insights: listCallCount === 1 ? [mkInsight()] : [] };
      },
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("Pilot ship date is slipping")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    await waitFor(() => expect(screen.queryByText("Pilot ship date is slipping")).toBeNull());
    const post = calls.find((c) => c.method === "POST")!;
    expect(post.url).toContain("/api/bff/engagements/e1/insights/i1/dismiss");
  });
});
