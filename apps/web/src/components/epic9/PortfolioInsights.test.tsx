import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { MatrixInsight } from "@/lib/bff/matrix-types";

import { PortfolioInsights } from "./PortfolioInsights.client";

function mkInsight(overrides: Partial<MatrixInsight> = {}): MatrixInsight {
  return {
    id: "pi1",
    tenant_id: "t1",
    engagement_id: null,
    agent: "master_strategist",
    insight_type: "recurring_risk_pattern",
    severity: "medium",
    title: "Data residency is a recurring risk",
    body: "Two engagements (Acme, Travis) flagged data residency concerns. Bundle a single counsel review.",
    citation_node_ids: ["n1", "n2"],
    citation_edge_ids: [],
    citation_event_ids: [],
    dedup_key: "master_strategist:t1:recurring_risk_pattern:...",
    status: "open",
    created_at: "2026-05-23T00:00:00Z",
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

describe("PortfolioInsights", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the empty state when no insights are returned", async () => {
    mockFetch({ "/portfolio/insights": () => ({ insights: [] }) });
    render(<PortfolioInsights />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText(/No portfolio insights yet/)).toBeTruthy();
  });

  it("renders a populated list with the cross-engagement insight body", async () => {
    mockFetch({ "/portfolio/insights": () => ({ insights: [mkInsight()] }) });
    render(<PortfolioInsights />);
    await waitFor(() =>
      expect(screen.getByText("Data residency is a recurring risk")).toBeTruthy(),
    );
    expect(screen.getByLabelText("severity medium")).toBeTruthy();
    expect(screen.getByText(/recurring risk pattern/i)).toBeTruthy();
    expect(screen.getByText(/Bundle a single counsel review/)).toBeTruthy();
  });

  it("refresh button POSTs to the refresh endpoint and updates the list", async () => {
    const calls = mockFetch({
      "/portfolio/insights/refresh": () => ({
        insights: [mkInsight({ title: "After refresh" })],
      }),
      "/portfolio/insights": () => ({ insights: [mkInsight({ title: "Before refresh" })] }),
    });
    render(<PortfolioInsights />);
    await waitFor(() => expect(screen.getByText("Before refresh")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /refresh portfolio insights/i }));
    await waitFor(() => expect(screen.getByText("After refresh")).toBeTruthy());
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toContain("/api/bff/portfolio/insights/refresh");
  });

  it("dismiss button POSTs to the per-insight dismiss endpoint and re-fetches", async () => {
    let listCallCount = 0;
    const calls = mockFetch({
      "/portfolio/insights/pi1/dismiss": () => ({
        insight: { ...mkInsight(), status: "dismissed" },
      }),
      "/portfolio/insights": () => {
        listCallCount += 1;
        return { insights: listCallCount === 1 ? [mkInsight()] : [] };
      },
    });
    render(<PortfolioInsights />);
    await waitFor(() =>
      expect(screen.getByText("Data residency is a recurring risk")).toBeTruthy(),
    );

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() =>
      expect(screen.queryByText("Data residency is a recurring risk")).toBeNull(),
    );
    const post = calls.find((c) => c.method === "POST");
    expect(post?.url).toContain("/api/bff/portfolio/insights/pi1/dismiss");
  });
});
