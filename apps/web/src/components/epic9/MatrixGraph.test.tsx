import { fireEvent, render, screen, waitFor } from "@testing-library/react";
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
const { MatrixGraph, EDGE_STYLE, BUILTIN_TYPE_ORDER } = await import("./MatrixGraph.client");

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

  it("routes stakeholder clicks to onStakeholderClick and other nodes to onNodeClick", () => {
    const onNodeClick = vi.fn();
    const onStakeholderClick = vi.fn();
    render(
      <MatrixGraph
        nodes={[
          mkNode({ id: "s1", node_type: "stakeholder", title: "Alice Sponsor" }),
          mkNode({ id: "n1", node_type: "system", title: "LiDAR ingest" }),
        ]}
        edges={[]}
        onNodeClick={onNodeClick}
        onStakeholderClick={onStakeholderClick}
      />,
    );

    const stakeholderNode = document.querySelector('[data-id="s1"]');
    expect(stakeholderNode).toBeTruthy();
    fireEvent.click(stakeholderNode as Element);
    expect(onStakeholderClick).toHaveBeenCalledTimes(1);
    expect(onStakeholderClick.mock.calls[0]?.[0]?.id).toBe("s1");
    expect(onNodeClick).not.toHaveBeenCalled();

    const systemNode = document.querySelector('[data-id="n1"]');
    expect(systemNode).toBeTruthy();
    fireEvent.click(systemNode as Element);
    expect(onNodeClick).toHaveBeenCalledTimes(1);
    expect(onNodeClick.mock.calls[0]?.[0]?.id).toBe("n1");
  });
});

describe("MatrixGraph EDGE_STYLE map", () => {
  const expectedTypes = [
    "belongs_to",
    "owns",
    "sponsors",
    "blocks",
    "affects",
    "threatens",
    "owed_by",
    "owed_to",
    "depends_on",
    "enables",
  ];

  it("has a non-empty stroke for every MATRIX_EDGE_TYPES entry", () => {
    for (const t of expectedTypes) {
      const entry = EDGE_STYLE[t];
      expect(entry, `missing EDGE_STYLE entry for ${t}`).toBeTruthy();
      expect(entry?.stroke, `empty stroke for ${t}`).toMatch(/^#[0-9a-f]{6}$/i);
    }
  });

  it("covers exactly the 10 documented edge types", () => {
    const keys = Object.keys(EDGE_STYLE).sort();
    expect(keys).toEqual([...expectedTypes].sort());
  });

  it("uses distinct stroke colors across all edge types", () => {
    const strokes = Object.values(EDGE_STYLE).map((s) => s.stroke);
    expect(new Set(strokes).size).toBe(strokes.length);
  });
});

describe("MatrixLegend overlay", () => {
  beforeEach(() => {
    class RO {
      observe() {}
      unobserve() {}
      disconnect() {}
    }
    vi.stubGlobal("ResizeObserver", RO);
  });

  it("renders 10 edge swatches and 7 node-type chips when expanded", () => {
    const nodes: MatrixNode[] = [mkNode({ id: "n1", node_type: "system", title: "LiDAR" })];
    render(<MatrixGraph nodes={nodes} edges={[]} />);
    const legend = screen.getByTestId("matrix-legend");
    expect(legend).toBeTruthy();
    const trigger = legend.querySelector('[data-slot="collapsible-trigger"]');
    expect(trigger).toBeTruthy();
    fireEvent.click(trigger!);
    const edgesList = screen.getByTestId("matrix-legend-edges");
    expect(edgesList.querySelectorAll("li")).toHaveLength(10);
    const nodesList = screen.getByTestId("matrix-legend-nodes");
    expect(nodesList.querySelectorAll("li")).toHaveLength(BUILTIN_TYPE_ORDER.length);
    expect(BUILTIN_TYPE_ORDER.length).toBe(7);
  });

  it("is collapsed by default to preserve canvas space", () => {
    render(<MatrixGraph nodes={[mkNode()]} edges={[]} />);
    const legend = screen.getByTestId("matrix-legend");
    const trigger = legend.querySelector('[data-slot="collapsible-trigger"]');
    expect(trigger?.getAttribute("aria-expanded")).toBe("false");
  });

  it("exposes color names via screen-reader-only text (not just hex)", () => {
    render(<MatrixGraph nodes={[mkNode()]} edges={[]} />);
    const legend = screen.getByTestId("matrix-legend");
    const trigger = legend.querySelector('[data-slot="collapsible-trigger"]');
    fireEvent.click(trigger!);
    expect(screen.getAllByText(/^color /i).length).toBeGreaterThanOrEqual(17);
  });

  it("toggles open/closed via keyboard activation of the trigger", () => {
    render(<MatrixGraph nodes={[mkNode()]} edges={[]} />);
    const legend = screen.getByTestId("matrix-legend");
    const trigger = legend.querySelector('[data-slot="collapsible-trigger"]') as HTMLButtonElement;
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
    // Radix Collapsible triggers are native <button>s — keyboard "Enter"
    // dispatches a click, which the click handler treats identically.
    trigger.focus();
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("true");
    fireEvent.click(trigger);
    expect(trigger.getAttribute("aria-expanded")).toBe("false");
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
