import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EvalHistorySection } from "@/components/admin/EvalHistorySection.client";
import type { EvalRun } from "@/lib/internal/eval-runs-cp";

function mkRun(overrides: Partial<EvalRun> = {}): EvalRun {
  return {
    id: "run-1",
    run_at: "2026-08-11T10:00:00Z",
    source: "ci",
    runtime: "langgraph",
    question_count: 30,
    pass_rate: 0.9,
    idk_rate: 0.2,
    hallucination_rate: 0.03,
    cross_engagement_leak_count: 0,
    p50_ms: 1200,
    p95_ms: 4100,
    ...overrides,
  };
}

function mockFetch(payload: unknown, ok = true) {
  const calls: string[] = [];
  const fetchMock = vi.fn((url: string) => {
    calls.push(url);
    return Promise.resolve({
      ok,
      status: ok ? 200 : 500,
      json: () => Promise.resolve(payload),
      text: () => Promise.resolve(""),
    });
  });
  vi.stubGlobal("fetch", fetchMock);
  return calls;
}

describe("EvalHistorySection", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("renders one table row per run with the summary columns", () => {
    const runs = [
      mkRun({ id: "run-a", pass_rate: 0.9 }),
      mkRun({ id: "run-b", pass_rate: 0.7, runtime: null, source: "local" }),
    ];
    render(<EvalHistorySection initialRuns={runs} initialError={null} />);

    expect(screen.getByTestId("eval-history-table")).toBeTruthy();
    const rowA = screen.getByTestId("eval-history-row-run-a");
    expect(rowA.textContent).toContain("ci");
    expect(rowA.textContent).toContain("langgraph");
    expect(rowA.textContent).toContain("30");
    expect(rowA.textContent).toContain("90.0");
    expect(rowA.textContent).toContain("3.0");

    // Null runtime renders a dash, not "null".
    const rowB = screen.getByTestId("eval-history-row-run-b");
    expect(rowB.textContent).toContain("—");
    expect(rowB.textContent).not.toContain("null");
  });

  it("red-highlights the leaks cell only when leaks > 0", () => {
    const runs = [
      mkRun({ id: "clean", cross_engagement_leak_count: 0 }),
      mkRun({ id: "leaky", cross_engagement_leak_count: 2 }),
    ];
    render(<EvalHistorySection initialRuns={runs} initialError={null} />);

    expect(screen.getByTestId("eval-history-leaks-clean").getAttribute("data-leaks")).toBe("ok");
    const leaky = screen.getByTestId("eval-history-leaks-leaky");
    expect(leaky.getAttribute("data-leaks")).toBe("red");
    expect(leaky.innerHTML).toContain("text-red-ink");
  });

  it("draws the pass-rate sparkline oldest-to-newest from the newest-first list", () => {
    // API order: newest (1.0) first. Chronological render: 0.5 → 1.0,
    // so the LAST polyline point must be the highest (smallest y).
    const runs = [
      mkRun({ id: "new", pass_rate: 1.0 }),
      mkRun({ id: "mid", pass_rate: 0.75 }),
      mkRun({ id: "old", pass_rate: 0.5 }),
    ];
    render(<EvalHistorySection initialRuns={runs} initialError={null} />);

    expect(screen.getByTestId("eval-history-sparkline")).toBeTruthy();
    const line = screen.getByTestId("eval-history-sparkline-line");
    const points = (line.getAttribute("points") ?? "")
      .split(" ")
      .map((p) => p.split(",").map(Number));
    expect(points.length).toBe(3);
    const [y0 = Number.NaN, y1 = Number.NaN, y2 = Number.NaN] = points.map(
      ([, y]) => y ?? Number.NaN,
    );
    // Rising pass rate → strictly falling y (SVG y grows downward).
    expect(y0).toBeGreaterThan(y1);
    expect(y1).toBeGreaterThan(y2);
  });

  it("renders a single-run sparkline without a polyline", () => {
    render(<EvalHistorySection initialRuns={[mkRun()]} initialError={null} />);
    expect(screen.getByTestId("eval-history-sparkline")).toBeTruthy();
    expect(screen.queryByTestId("eval-history-sparkline-line")).toBeNull();
  });

  it("explains how runs get recorded in the empty state", () => {
    render(<EvalHistorySection initialRuns={[]} initialError={null} />);
    const empty = screen.getByTestId("eval-history-empty");
    expect(empty.textContent).toContain("--persist-url");
    expect(empty.textContent).toContain("/internal/v1/admin/eval-runs");
  });

  it("refreshes via the admin BFF and renders the new rows", async () => {
    const calls = mockFetch({ runs: [mkRun({ id: "fresh" })] });
    render(<EvalHistorySection initialRuns={[]} initialError={null} />);

    fireEvent.click(screen.getByTestId("eval-history-refresh"));

    await waitFor(() => {
      expect(screen.getByTestId("eval-history-row-fresh")).toBeTruthy();
    });
    expect(calls[0]).toContain("/api/bff/admin/eval-runs?limit=50");
  });

  it("surfaces an error from a failed refresh", async () => {
    mockFetch(null, false);
    render(<EvalHistorySection initialRuns={[mkRun()]} initialError={null} />);
    fireEvent.click(screen.getByTestId("eval-history-refresh"));
    await waitFor(() => {
      expect(screen.getByRole("alert").textContent).toMatch(/Could not load eval history/);
    });
  });

  it("shows the initial error from the server page", () => {
    render(<EvalHistorySection initialRuns={null} initialError="CP unreachable" />);
    expect(screen.getByRole("alert").textContent).toContain("CP unreachable");
  });
});
