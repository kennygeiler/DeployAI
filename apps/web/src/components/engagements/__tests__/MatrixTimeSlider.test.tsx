import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

const { routerReplaceMock, pathnameMock, searchParamsRef } = vi.hoisted(() => ({
  routerReplaceMock: vi.fn(),
  pathnameMock: vi.fn(),
  searchParamsRef: { current: new URLSearchParams() as URLSearchParams },
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: routerReplaceMock,
    push: vi.fn(),
    back: vi.fn(),
    forward: vi.fn(),
  }),
  usePathname: () => pathnameMock(),
  useSearchParams: () => searchParamsRef.current,
}));

import { MatrixTimeSlider } from "@/components/engagements/MatrixTimeSlider.client";

describe("MatrixTimeSlider", () => {
  beforeEach(() => {
    pathnameMock.mockReturnValue("/engagements/e1");
    searchParamsRef.current = new URLSearchParams();
  });

  afterEach(() => {
    routerReplaceMock.mockReset();
  });

  it("renders the slider with 'Live' label and no Return-to-live CTA by default", () => {
    render(<MatrixTimeSlider todayOverride="2026-05-25" earliestDate="2026-05-20" />);

    expect(screen.getByTestId("matrix-time-slider")).toBeTruthy();
    expect(screen.getByLabelText(/Matrix snapshot date/i)).toBeTruthy();
    expect(screen.getByTestId("matrix-time-slider-value").textContent).toBe("Live");
    expect(screen.queryByRole("button", { name: /Return to live/i })).toBeNull();
  });

  it("pushes ?at=YYYY-MM-DD to the URL when the user selects a day", () => {
    render(<MatrixTimeSlider todayOverride="2026-05-25" earliestDate="2026-05-20" />);
    const input = screen.getByLabelText(/Matrix snapshot date/i) as HTMLInputElement;

    // earliest = 2026-05-20 (index 0), today = 2026-05-25 (index 5).
    // Index 2 = 2026-05-22.
    fireEvent.change(input, { target: { value: "2" } });

    expect(routerReplaceMock).toHaveBeenCalledTimes(1);
    const [target] = routerReplaceMock.mock.calls[0]!;
    expect(target).toBe("/engagements/e1?at=2026-05-22");
  });

  it("renders the selected date and the Return-to-live CTA when at is set", () => {
    searchParamsRef.current = new URLSearchParams("at=2026-05-22");
    render(<MatrixTimeSlider todayOverride="2026-05-25" earliestDate="2026-05-20" />);

    expect(screen.getByTestId("matrix-time-slider-value").textContent).toBe("2026-05-22");
    expect(screen.getByRole("button", { name: /Return to live/i })).toBeTruthy();
  });

  it("clears ?at when 'Return to live' is clicked", () => {
    searchParamsRef.current = new URLSearchParams("at=2026-05-22");
    render(<MatrixTimeSlider todayOverride="2026-05-25" earliestDate="2026-05-20" />);

    fireEvent.click(screen.getByRole("button", { name: /Return to live/i }));

    expect(routerReplaceMock).toHaveBeenCalledTimes(1);
    const [target] = routerReplaceMock.mock.calls[0]!;
    expect(target).toBe("/engagements/e1");
  });

  it("clears ?at when the slider is dragged back to today", () => {
    searchParamsRef.current = new URLSearchParams("at=2026-05-22");
    render(<MatrixTimeSlider todayOverride="2026-05-25" earliestDate="2026-05-20" />);

    const input = screen.getByLabelText(/Matrix snapshot date/i) as HTMLInputElement;
    // Total days = 5, so index 5 = today.
    fireEvent.change(input, { target: { value: "5" } });

    const [target] = routerReplaceMock.mock.calls[0]!;
    expect(target).toBe("/engagements/e1");
  });

  it("preserves other query params when updating at", () => {
    searchParamsRef.current = new URLSearchParams("tab=matrix&at=2026-05-22");
    render(<MatrixTimeSlider todayOverride="2026-05-25" earliestDate="2026-05-20" />);

    fireEvent.click(screen.getByRole("button", { name: /Return to live/i }));

    const [target] = routerReplaceMock.mock.calls[0]!;
    expect(target).toBe("/engagements/e1?tab=matrix");
  });
});

// ReactFlow needs ResizeObserver + a non-zero getBoundingClientRect.
beforeAll(() => {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", RO);
  if (!Element.prototype.getBoundingClientRect.toString().includes("[stub]")) {
    Element.prototype.getBoundingClientRect = function stub() {
      return {
        x: 0,
        y: 0,
        width: 100,
        height: 50,
        top: 0,
        left: 0,
        right: 100,
        bottom: 50,
        toJSON: () => ({}),
      } as DOMRect;
    } as typeof Element.prototype.getBoundingClientRect;
  }
});

const { MatrixGraph } = await import("@/components/epic9/MatrixGraph.client");

function mkNode(): MatrixNode {
  return {
    id: "live-1",
    engagement_id: "e1",
    node_type: "system",
    title: "Live system",
    identity_node_id: null,
    attributes: {},
    status: null,
    evidence_event_ids: [],
    created_at: "2026-05-25T00:00:00Z",
    updated_at: "2026-05-25T00:00:00Z",
  };
}

describe("MatrixGraph + slider integration", () => {
  beforeEach(() => {
    pathnameMock.mockReturnValue("/engagements/e1");
    searchParamsRef.current = new URLSearchParams();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    routerReplaceMock.mockReset();
  });

  it("propagates a snapshot 404 from the BFF into a 'No snapshot for that date' banner", async () => {
    searchParamsRef.current = new URLSearchParams("at=2026-05-22");
    // jsdom path: stub fetch so we don't make a real network call.
    // ReactFlow still needs ResizeObserver / getBoundingClientRect; see beforeAll above.
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: false,
          status: 404,
          json: () => Promise.resolve({ error: "not_found" }),
          text: () => Promise.resolve(""),
        }),
      ),
    );

    const nodes: MatrixNode[] = [mkNode()];
    const edges: MatrixEdge[] = [];

    render(<MatrixGraph engagementId="e1" nodes={nodes} edges={edges} customTypes={[]} />);

    await waitFor(() => {
      expect(screen.getByTestId("matrix-snapshot-missing")).toBeTruthy();
    });
    expect(screen.getByText(/No snapshot for that date/i)).toBeTruthy();
    // The graph itself is not rendered when the snapshot is missing — the
    // live data was suppressed in favour of the banner, no crash.
    expect(screen.queryByTestId("matrix-graph")).toBeNull();
  });
});
