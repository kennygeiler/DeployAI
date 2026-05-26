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
    expect(screen.getAllByLabelText("severity high")[0]).toBeTruthy();
    expect(screen.getByText(/Confirm a new date/)).toBeTruthy();
    // Kind renders human-readable on the group header.
    expect(screen.getByText("Stale commitment")).toBeTruthy();
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

  it("refresh clears a stale error banner on success", async () => {
    const calls: Array<{ url: string; method: string }> = [];
    const fetchMock = vi.fn((url: string, init?: { method?: string }) => {
      const method = init?.method ?? "GET";
      calls.push({ url, method });
      if (method === "POST" && url.includes("/insights/refresh")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ insights: [mkInsight({ title: "After refresh" })] }),
        });
      }
      // First GET fails so the err banner shows.
      return Promise.resolve({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ detail: "boom" }),
        text: () => Promise.resolve("boom"),
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());
    // Error banner is visible after the failed mount fetch.
    await waitFor(() => expect(screen.getByText(/boom|Could not load/)).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: /refresh insights/i }));

    await waitFor(() => expect(screen.getByText("After refresh")).toBeTruthy());
    // Stale error banner must be gone after a successful refresh.
    expect(screen.queryByText(/boom|Could not load/)).toBeNull();
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

  it("groups insights by kind, severity-first, with critical/warning open and info collapsed", async () => {
    mockFetch({
      "/insights": () => ({
        insights: [
          mkInsight({
            id: "c1",
            insight_type: "stale_commitment",
            severity: "high",
            title: "Critical 1",
            body: "Critical body 1",
          }),
          mkInsight({
            id: "w1",
            insight_type: "decision_cycle_slowdown",
            severity: "medium",
            title: "Warning 1",
            body: "Warning body 1",
          }),
          mkInsight({
            id: "i1",
            insight_type: "ambient_observation",
            severity: "low",
            title: "Info 1",
            body: "Info body 1",
          }),
        ],
      }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.queryByText("Loading…")).toBeNull());

    // Collapsible triggers expose aria-expanded; the Refresh button does not.
    const groupTriggers = screen
      .getAllByRole("button")
      .filter((h) => h.hasAttribute("aria-expanded"));
    expect(groupTriggers).toHaveLength(3);

    const [critical, warning, info] = groupTriggers as [HTMLElement, HTMLElement, HTMLElement];
    // Severity-first order: critical, warning, info.
    expect(critical.textContent).toContain("Stale commitment");
    expect(warning.textContent).toContain("Decision cycle slowdown");
    expect(info.textContent).toContain("Ambient observation");

    // Critical + warning open by default, info collapsed.
    expect(critical.getAttribute("aria-expanded")).toBe("true");
    expect(warning.getAttribute("aria-expanded")).toBe("true");
    expect(info.getAttribute("aria-expanded")).toBe("false");

    // Open-group bodies are in the DOM; collapsed info body is not rendered as text.
    expect(screen.getByText("Critical 1")).toBeTruthy();
    expect(screen.getByText("Warning 1")).toBeTruthy();
    expect(screen.queryByText("Info body 1")).toBeNull();
  });

  it("clicking a chevron toggles aria-expanded without losing scroll position", async () => {
    mockFetch({
      "/insights": () => ({
        insights: [
          mkInsight({
            id: "c1",
            insight_type: "stale_commitment",
            severity: "high",
            title: "Critical 1",
            body: "Critical body 1",
          }),
        ],
      }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("Stale commitment")).toBeTruthy());

    const trigger = screen
      .getAllByRole("button", { expanded: true })
      .find((h) => h.textContent?.includes("Stale commitment"))!;
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    expect(trigger.getAttribute("aria-controls")).toBeTruthy();

    const beforeScroll = window.scrollY;
    const user = userEvent.setup();
    await user.click(trigger);
    await waitFor(() => expect(trigger.getAttribute("aria-expanded")).toBe("false"));
    expect(window.scrollY).toBe(beforeScroll);

    await user.click(trigger);
    await waitFor(() => expect(trigger.getAttribute("aria-expanded")).toBe("true"));
  });

  it("invokes onExplain stub when the per-card Explain button is clicked", async () => {
    mockFetch({
      "/insights": () => ({ insights: [mkInsight({ id: "ix1" })] }),
    });
    const onExplain = vi.fn();
    render(<EngagementInsights engagementId="e1" onExplain={onExplain} />);
    await waitFor(() => expect(screen.getByText("Pilot ship date is slipping")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Explain" }));
    expect(onExplain).toHaveBeenCalledOnce();
    const firstCall = onExplain.mock.calls[0];
    if (!firstCall) throw new Error("onExplain was not called");
    expect((firstCall[0] as MatrixInsight).id).toBe("ix1");
  });
});
