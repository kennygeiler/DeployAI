import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { UnifiedInsight } from "@/lib/bff/insight-types";

import { EngagementInsights } from "./EngagementInsights.client";

function mkInsight(overrides: Partial<UnifiedInsight> = {}): UnifiedInsight {
  return {
    id: "i1",
    model: "matrix",
    engagement_id: "e1",
    insight_type: "stale_commitment",
    severity: "high",
    title: "Pilot ship date is slipping",
    body: "Commitment cited 35 days ago. Confirm a new date with the sponsor by EOD.",
    status: "open",
    created_at: "2026-05-09T00:00:00Z",
    snoozed_until: null,
    ...overrides,
  };
}

function mkTemporal(overrides: Partial<UnifiedInsight> = {}): UnifiedInsight {
  return mkInsight({
    id: "t1",
    model: "temporal",
    insight_type: "engagement_silence",
    severity: "medium",
    title: "No activity in 21 days",
    body: "Trailing silence across all channels.",
    ...overrides,
  });
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
    vi.restoreAllMocks();
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

  it("renders both models with source badges (F2 unification)", async () => {
    mockFetch({
      "/insights": () => ({ insights: [mkInsight(), mkTemporal()] }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("Pilot ship date is slipping")).toBeTruthy());
    expect(screen.getByText("No activity in 21 days")).toBeTruthy();
    expect(screen.getByLabelText("source oracle")).toBeTruthy();
    expect(screen.getByLabelText("source temporal")).toBeTruthy();
  });

  it("refresh button calls the refresh endpoint and re-lists", async () => {
    let listCallCount = 0;
    const calls = mockFetch({
      "/insights/refresh": () => ({ insights: [] }),
      "/insights": () => {
        listCallCount += 1;
        return {
          insights: [
            mkInsight({ title: listCallCount === 1 ? "Before refresh" : "After refresh" }),
          ],
        };
      },
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
    let failList = true;
    const fetchMock = vi.fn((url: string, init?: { method?: string }) => {
      const method = init?.method ?? "GET";
      if (method === "POST" && url.includes("/insights/refresh")) {
        failList = false;
        return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
      }
      if (failList) {
        return Promise.resolve({
          ok: false,
          status: 500,
          json: () => Promise.resolve({ detail: "boom" }),
          text: () => Promise.resolve("boom"),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ insights: [mkInsight({ title: "After refresh" })] }),
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

  it("dismiss on a matrix row POSTs without the temporal model param", async () => {
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
    expect(post.url).not.toContain("model=temporal");
  });

  it("resolve on a temporal row targets the temporal backend", async () => {
    const calls = mockFetch({
      "/insights/t1/resolve": () => ({ insight: { ...mkTemporal(), status: "resolved" } }),
      "/insights": () => ({ insights: [mkTemporal()] }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("No activity in 21 days")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Resolve" }));

    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST");
      expect(post?.url).toContain("/insights/t1/resolve?model=temporal");
    });
  });

  it("snooze on a temporal row prompts for days and POSTs to the snooze route", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("14");
    const calls = mockFetch({
      "/insights/t1/snooze": () => ({ snooze: { insight_id: "t1", status: "snoozed" } }),
      "/insights": () => ({ insights: [mkTemporal()] }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("No activity in 21 days")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Snooze" }));

    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST");
      expect(post?.url).toContain("/api/bff/engagements/e1/insights/t1/snooze");
    });
  });

  it("follow-up on a temporal row prompts for a due date and POSTs it", async () => {
    vi.spyOn(window, "prompt").mockReturnValue("2026-09-01");
    const calls = mockFetch({
      "/insights/t1/followup": () => ({ followup: { action_queue_item_id: "fu-1" } }),
      "/insights": () => ({ insights: [mkTemporal()] }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("No activity in 21 days")).toBeTruthy());

    const user = userEvent.setup();
    await user.click(screen.getByRole("button", { name: "Follow up" }));

    await waitFor(() => {
      const post = calls.find((c) => c.method === "POST");
      expect(post?.url).toContain("/api/bff/engagements/e1/insights/t1/followup");
    });
  });

  it("matrix rows do not offer snooze / follow-up", async () => {
    mockFetch({
      "/insights": () => ({ insights: [mkInsight()] }),
    });
    render(<EngagementInsights engagementId="e1" />);
    await waitFor(() => expect(screen.getByText("Pilot ship date is slipping")).toBeTruthy());
    expect(screen.queryByRole("button", { name: "Snooze" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Follow up" })).toBeNull();
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
    expect((firstCall[0] as UnifiedInsight).id).toBe("ix1");
  });
});
