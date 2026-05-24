import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Recommendation } from "@/lib/internal/recommendations-cp";

import { RecommendationsPanel } from "./RecommendationsPanel.client";

function mkRec(overrides: Partial<Recommendation> = {}): Recommendation {
  return {
    id: "rec1",
    role: "biz_dev",
    priority: "high",
    title: "Risk Vendor delay has no mitigation commitment",
    body: "Surface to legal/exec and capture an owner.",
    citation_node_ids: ["n1"],
    citation_edge_ids: [],
    ...overrides,
  };
}

function mockFetch(handler: () => unknown, ok = true) {
  const calls: Array<{ url: string; method: string }> = [];
  const fetchMock = vi.fn((url: string, init?: { method?: string }) => {
    calls.push({ url, method: init?.method ?? "GET" });
    return Promise.resolve({
      ok,
      json: () => Promise.resolve(handler()),
      text: () => Promise.resolve(typeof handler() === "string" ? String(handler()) : ""),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("RecommendationsPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the empty state when the BFF returns no recommendations", async () => {
    mockFetch(() => ({ recommendations: [] }));
    render(<RecommendationsPanel engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText(/No outstanding actions/)).toBeTruthy();
  });

  it("groups cards by priority (high before medium before low)", async () => {
    mockFetch(() => ({
      recommendations: [
        mkRec({ id: "h1", priority: "high", title: "High one", role: "biz_dev" }),
        mkRec({ id: "m1", priority: "medium", title: "Medium one", role: "deployment_strategist" }),
        mkRec({ id: "l1", priority: "low", title: "Low one", role: "fde" }),
      ],
    }));
    render(<RecommendationsPanel engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("High one")).toBeTruthy());

    expect(screen.getByText("High priority")).toBeTruthy();
    expect(screen.getByText("Medium priority")).toBeTruthy();
    expect(screen.getByText("Low priority")).toBeTruthy();

    // Verify ordering by checking DOM index of the priority group headers.
    const allHeadings = screen.getAllByRole("heading", { level: 3 });
    const labels = allHeadings.map((h) => h.textContent);
    expect(labels.indexOf("High priority")).toBeLessThan(labels.indexOf("Medium priority"));
    expect(labels.indexOf("Medium priority")).toBeLessThan(labels.indexOf("Low priority"));
  });

  it("renders role + priority badges on each card", async () => {
    mockFetch(() => ({
      recommendations: [
        mkRec({ id: "h1", priority: "high", role: "biz_dev", title: "Risk thing" }),
        mkRec({
          id: "m1",
          priority: "medium",
          role: "deployment_strategist",
          title: "Decision thing",
        }),
      ],
    }));
    render(<RecommendationsPanel engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("Risk thing")).toBeTruthy());

    expect(screen.getByLabelText("role biz_dev")).toBeTruthy();
    expect(screen.getByLabelText("role deployment_strategist")).toBeTruthy();
    expect(screen.getByLabelText("priority high")).toBeTruthy();
    expect(screen.getByLabelText("priority medium")).toBeTruthy();
    // BizDev label visible
    expect(screen.getAllByText("BizDev").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Strategist").length).toBeGreaterThanOrEqual(1);
  });

  it("renders the error inline when the BFF returns a non-OK response", async () => {
    mockFetch(() => "cp engagement recommendations 500: boom", false);
    render(<RecommendationsPanel engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    expect(screen.getByText(/recommendations/i)).toBeTruthy();
    // Empty / cards must not render when there is an error.
    expect(screen.queryByText(/No outstanding actions/)).toBeNull();
  });
});
