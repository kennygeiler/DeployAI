import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

const { routerReplaceMock, pathnameMock, searchParamsRef } = vi.hoisted(() => ({
  routerReplaceMock: vi.fn(),
  pathnameMock: vi.fn(() => "/engagements/e1"),
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

// jsdom doesn't ship ResizeObserver / DOMMatrixReadOnly / requestAnimationFrame
// in the shape ReactFlow expects. Stub them before importing the component.
beforeAll(() => {
  class RO {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", RO);
  // ReactFlow measures node sizes; jsdom returns 0/0 — give it deterministic
  // numbers so the layout pass doesn't NaN out.
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

// Import AFTER the stubs land.
const { MatrixGraph } = await import("./MatrixGraph.client");

function mkNode(overrides: Partial<MatrixNode> = {}): MatrixNode {
  return {
    id: "n1",
    engagement_id: "e1",
    node_type: "system",
    title: "LiDAR ingest",
    identity_node_id: null,
    attributes: {},
    status: null,
    evidence_event_ids: [],
    created_at: "2026-05-09T00:00:00Z",
    updated_at: "2026-05-09T00:00:00Z",
    ...overrides,
  };
}

function mkEdge(overrides: Partial<MatrixEdge> = {}): MatrixEdge {
  return {
    id: "e1",
    engagement_id: "e1",
    edge_type: "threatens",
    from_node_id: "n1",
    to_node_id: "n2",
    attributes: {},
    evidence_event_ids: [],
    created_at: "2026-05-09T00:00:00Z",
    updated_at: "2026-05-09T00:00:00Z",
    ...overrides,
  };
}

describe("MatrixGraph", () => {
  it("renders the empty-state copy when no nodes exist", () => {
    render(<MatrixGraph nodes={[]} edges={[]} />);
    expect(screen.getByText(/No matrix entities yet/)).toBeTruthy();
  });

  it("renders the graph surface and the node labels when nodes exist", () => {
    const nodes: MatrixNode[] = [
      mkNode({ id: "n1", node_type: "system", title: "LiDAR ingest" }),
      mkNode({ id: "n2", node_type: "risk", title: "Calibration slip" }),
    ];
    const edges: MatrixEdge[] = [
      mkEdge({ id: "e1", from_node_id: "n2", to_node_id: "n1", edge_type: "threatens" }),
    ];
    render(<MatrixGraph nodes={nodes} edges={edges} />);
    // Container is the figure shell — ReactFlow renders its own subtree inside.
    expect(screen.getByTestId("matrix-graph")).toBeTruthy();
    expect(screen.getByRole("figure", { name: /deployment matrix/i })).toBeTruthy();
    // Node labels are rendered as plain text inside RF nodes.
    expect(screen.getByText("LiDAR ingest")).toBeTruthy();
    expect(screen.getByText("Calibration slip")).toBeTruthy();
    // Column header for the type the node belongs to.
    expect(screen.getByText(/Systems/)).toBeTruthy();
    expect(screen.getByText(/Risks/)).toBeTruthy();
  });

  // Edge rendering is intentionally not asserted here — ReactFlow draws edges
  // via SVG paths whose layout depends on container size, and jsdom returns
  // zero dimensions. Edges are covered by manual smoke-test against a real
  // browser. The graph-shell test above proves nodes + columns wire up.

  it("hides columns for node types that aren't present", () => {
    render(
      <MatrixGraph nodes={[mkNode({ node_type: "risk", title: "Only a risk" })]} edges={[]} />,
    );
    // Risk column is in.
    expect(screen.getByText(/Risks/)).toBeTruthy();
    // Stakeholder / Systems / Decisions columns are NOT rendered when empty.
    expect(screen.queryByText(/Stakeholders/)).toBeNull();
    expect(screen.queryByText(/Systems/)).toBeNull();
    expect(screen.queryByText(/Decisions/)).toBeNull();
  });

  it("renders a custom-type column when the tenant has one registered", () => {
    render(
      <MatrixGraph
        nodes={[mkNode({ node_type: "patient_journey", title: "Surgery prep" })]}
        edges={[]}
        customTypes={[{ name: "patient_journey", label: "Patient journeys", color: "#fde68a" }]}
      />,
    );
    expect(screen.getByText("Surgery prep")).toBeTruthy();
    expect(screen.getByText(/Patient journeys/)).toBeTruthy();
  });
});

describe("MatrixGraph stale-snapshot banner", () => {
  beforeEach(() => {
    pathnameMock.mockReturnValue("/engagements/e1");
    searchParamsRef.current = new URLSearchParams("at=2026-05-01");
    class RO {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", RO);
  });

  afterEach(() => {
    routerReplaceMock.mockReset();
  });

  function stubSnapshotFetch(capturedAt: string): void {
    vi.stubGlobal(
      "fetch",
      vi.fn(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () =>
            Promise.resolve({
              snapshot: {
                captured_at: capturedAt,
                nodes: [mkNode({ id: "snap-1", title: "Snapshot system" })],
                edges: [],
              },
            }),
          text: () => Promise.resolve(""),
        }),
      ),
    );
  }

  it("shows the banner when captured_at predates the newest live updated_at by > 1 day", async () => {
    stubSnapshotFetch("2026-05-01T00:00:00Z");
    const liveNodes = [mkNode({ id: "live-1", updated_at: "2026-05-10T00:00:00Z" })];

    render(<MatrixGraph engagementId="e1" nodes={liveNodes} edges={[]} />);

    await waitFor(() => {
      expect(screen.getByTestId("matrix-snapshot-stale-banner")).toBeTruthy();
    });
    expect(screen.getByText(/Snapshot from 2026-05-01/)).toBeTruthy();
    expect(screen.getByText(/matrix has changed since/)).toBeTruthy();
  });

  it("hides the banner when the gap is exactly 1 day (boundary)", async () => {
    stubSnapshotFetch("2026-05-09T00:00:00Z");
    const liveNodes = [mkNode({ id: "live-1", updated_at: "2026-05-10T00:00:00Z" })];

    render(<MatrixGraph engagementId="e1" nodes={liveNodes} edges={[]} />);

    await waitFor(() => {
      expect(screen.getByTestId("matrix-graph")).toBeTruthy();
    });
    expect(screen.queryByTestId("matrix-snapshot-stale-banner")).toBeNull();
  });

  it("hides the banner when no live nodes exist (cannot determine staleness)", async () => {
    stubSnapshotFetch("2026-05-01T00:00:00Z");

    render(<MatrixGraph engagementId="e1" nodes={[]} edges={[]} />);

    await waitFor(() => {
      expect(screen.getByTestId("matrix-graph")).toBeTruthy();
    });
    expect(screen.queryByTestId("matrix-snapshot-stale-banner")).toBeNull();
  });
});
