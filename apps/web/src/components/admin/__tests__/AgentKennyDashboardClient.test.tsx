import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  AgentKennyDashboardClient,
  hallucinationTrafficLight,
} from "@/components/admin/AgentKennyDashboardClient";
import type { AgentKennyDashboard } from "@/lib/internal/agent-kenny-dashboard-cp";

function mkDashboard(overrides: Partial<AgentKennyDashboard> = {}): AgentKennyDashboard {
  return {
    window_days: 7,
    hallucination_rate: 0.01,
    citations_total: 100,
    citations_unverified: 1,
    latency_p50_ms: 200,
    latency_p95_ms: 800,
    latency_p99_ms: 1500,
    idk_rate: 0.05,
    tool_calls: [
      { tool: "matrix.query", count: 12 },
      { tool: "ledger.search", count: 7 },
    ],
    lint_flag_counts: [
      { kind: "contradiction", count: 3, most_recent: "2026-05-25T10:00:00Z" },
      { kind: "stale", count: 1, most_recent: "2026-05-24T09:00:00Z" },
    ],
    top_cited_events: [
      { event_id: "evt-1", summary: "Email: kickoff for project X", citation_count: 5 },
      { event_id: "evt-2", summary: "Meeting: weekly sync", citation_count: 3 },
    ],
    adversarial_concerns_total: 4,
    ...overrides,
  };
}

function mockFetch(payload: AgentKennyDashboard | null, ok = true) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    return Promise.resolve({
      ok,
      status: ok ? 200 : 500,
      json: () => Promise.resolve(payload ?? mkDashboard()),
      text: () => Promise.resolve(""),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("hallucinationTrafficLight", () => {
  it("returns green below 2%", () => {
    expect(hallucinationTrafficLight(0).level).toBe("green");
    expect(hallucinationTrafficLight(0.0199).level).toBe("green");
  });

  it("returns amber between 2% and 5% inclusive of the low bound", () => {
    expect(hallucinationTrafficLight(0.02).level).toBe("amber");
    expect(hallucinationTrafficLight(0.05).level).toBe("amber");
  });

  it("returns red above 5%", () => {
    expect(hallucinationTrafficLight(0.0501).level).toBe("red");
    expect(hallucinationTrafficLight(0.5).level).toBe("red");
  });
});

describe("AgentKennyDashboardClient", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders the four metric cards with the initial data", () => {
    const data = mkDashboard();
    render(<AgentKennyDashboardClient tenantId="t1" initialData={data} initialError={null} />);
    const cards = screen.getByTestId("agent-kenny-dashboard-cards");
    expect(cards).toBeTruthy();
    expect(screen.getByTestId("agent-kenny-dashboard-card-hallucination")).toBeTruthy();
    expect(screen.getByTestId("agent-kenny-dashboard-card-latency")).toBeTruthy();
    expect(screen.getByTestId("agent-kenny-dashboard-card-idk")).toBeTruthy();
    expect(screen.getByTestId("agent-kenny-dashboard-card-adversarial")).toBeTruthy();

    // Hallucination value formatted as %
    const hv = screen.getByTestId("agent-kenny-dashboard-hallucination-value");
    expect(hv.textContent).toMatch(/1\.0%/);

    // Latency p99
    expect(screen.getByTestId("agent-kenny-dashboard-latency-p99").textContent).toContain("1500");
  });

  it("tags the hallucination card with the correct traffic-light level", () => {
    render(
      <AgentKennyDashboardClient
        tenantId="t1"
        initialData={mkDashboard({ hallucination_rate: 0.07 })}
        initialError={null}
      />,
    );
    const card = screen.getByTestId("agent-kenny-dashboard-card-hallucination");
    expect(card.getAttribute("data-traffic-light")).toBe("red");
  });

  it("renders the empty state when no data and no error", () => {
    render(<AgentKennyDashboardClient tenantId="t1" initialData={null} initialError={null} />);
    expect(screen.getByTestId("agent-kenny-dashboard-empty")).toBeTruthy();
  });

  it("renders the empty-state body sections when each list is empty", () => {
    const data = mkDashboard({
      tool_calls: [],
      lint_flag_counts: [],
      top_cited_events: [],
    });
    render(<AgentKennyDashboardClient tenantId="t1" initialData={data} initialError={null} />);
    expect(screen.getByTestId("agent-kenny-dashboard-tools").textContent).toContain(
      "No tool calls",
    );
    expect(screen.getByTestId("agent-kenny-dashboard-lint").textContent).toContain("No lint flags");
    expect(screen.getByTestId("agent-kenny-dashboard-top-cited").textContent).toContain(
      "No citations",
    );
  });

  it("re-fetches via the BFF when the window selector changes", async () => {
    const calls = mockFetch(mkDashboard({ window_days: 30 }));
    render(
      <AgentKennyDashboardClient
        tenantId="tenant-abc"
        initialData={mkDashboard()}
        initialError={null}
      />,
    );

    fireEvent.click(screen.getByTestId("agent-kenny-dashboard-window-30"));

    await waitFor(() => {
      expect(calls.length).toBeGreaterThan(0);
    });
    expect(calls[0]).toContain(
      "/api/internal/v1/tenants/tenant-abc/agent_kenny_dashboard?window_days=30",
    );
  });

  it("surfaces an error from a failed refresh", async () => {
    mockFetch(null, false);
    render(
      <AgentKennyDashboardClient tenantId="t1" initialData={mkDashboard()} initialError={null} />,
    );
    fireEvent.click(screen.getByTestId("agent-kenny-dashboard-refresh"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/Could not load dashboard/);
    });
  });
});
