import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
    const graph = screen.getByTestId("matrix-graph");
    expect(graph).toBeTruthy();
    expect(screen.getByRole("figure", { name: /deployment matrix/i })).toBeTruthy();
    // Node labels are rendered as plain text inside RF nodes.
    expect(screen.getByText("LiDAR ingest")).toBeTruthy();
    expect(screen.getByText("Calibration slip")).toBeTruthy();
    // Column header for the type the node belongs to (scoped to the canvas —
    // the U5 type-filter chips repeat the type labels outside it).
    expect(within(graph).getByText(/Systems/)).toBeTruthy();
    expect(within(graph).getByText(/Risks/)).toBeTruthy();
  });

  // Edge rendering is intentionally not asserted here — ReactFlow draws edges
  // via SVG paths whose layout depends on container size, and jsdom returns
  // zero dimensions. Edges are covered by manual smoke-test against a real
  // browser. The graph-shell test above proves nodes + columns wire up.

  it("hides columns for node types that aren't present", () => {
    render(
      <MatrixGraph nodes={[mkNode({ node_type: "risk", title: "Only a risk" })]} edges={[]} />,
    );
    // Risk column is in (scoped to the canvas; the filter chip repeats it).
    const graph = screen.getByTestId("matrix-graph");
    expect(within(graph).getByText(/Risks/)).toBeTruthy();
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
    expect(within(screen.getByTestId("matrix-graph")).getByText(/Patient journeys/)).toBeTruthy();
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

/**
 * Deterministic over-threshold fixture for the U5 lens suite (81 nodes > 60):
 * - "Hub stakeholder" (s-hub) linked to System 0..9 and Risk 1 → the
 *   highest-degree stakeholder, so it is the default lens focus.
 * - Risk 0 hangs off System 0 → exactly 2 hops from the hub.
 * - "Distant system" has no edges → only reachable via search or full graph.
 */
function mkLensFixture(): { nodes: MatrixNode[]; edges: MatrixEdge[] } {
  const nodes: MatrixNode[] = [
    mkNode({ id: "s-hub", node_type: "stakeholder", title: "Hub stakeholder" }),
    mkNode({ id: "s-quiet", node_type: "stakeholder", title: "Quiet stakeholder" }),
    mkNode({ id: "sys-distant", node_type: "system", title: "Distant system" }),
  ];
  const edges: MatrixEdge[] = [];
  for (let i = 0; i < 70; i++) {
    nodes.push(mkNode({ id: `sys-${i}`, node_type: "system", title: `System ${i}` }));
  }
  for (let i = 0; i < 8; i++) {
    nodes.push(mkNode({ id: `risk-${i}`, node_type: "risk", title: `Risk ${i}` }));
  }
  for (let i = 0; i < 10; i++) {
    edges.push(mkEdge({ id: `e-hub-${i}`, from_node_id: "s-hub", to_node_id: `sys-${i}` }));
  }
  edges.push(
    mkEdge({ id: "e-hub-risk", from_node_id: "s-hub", to_node_id: "risk-1", edge_type: "owns" }),
  );
  edges.push(mkEdge({ id: "e-quiet", from_node_id: "s-quiet", to_node_id: "sys-0" }));
  edges.push(
    mkEdge({ id: "e-2hop", from_node_id: "risk-0", to_node_id: "sys-0", edge_type: "threatens" }),
  );
  return { nodes, edges };
}

describe("MatrixGraph lens view (U5)", () => {
  beforeEach(() => {
    pathnameMock.mockReturnValue("/engagements/e1");
    searchParamsRef.current = new URLSearchParams();
  });

  it("defaults to the lens focused on the highest-degree stakeholder when over threshold", () => {
    const { nodes, edges } = mkLensFixture();
    render(<MatrixGraph nodes={nodes} edges={edges} />);

    const status = screen.getByTestId("matrix-lens-status");
    expect(status.textContent).toContain("Hub stakeholder");
    // 1-hop neighborhood: hub + System 0..9 + Risk 1 = 12 of 81.
    expect(status.textContent).toContain("showing 12 of 81 nodes");
    // Focus + a direct neighbor render; an unconnected node does not.
    expect(screen.getByText("Hub stakeholder")).toBeTruthy();
    expect(screen.getByText("System 3")).toBeTruthy();
    expect(screen.queryByText("Distant system")).toBeNull();
    // 2-hop-only node is hidden at the default depth of 1.
    expect(screen.queryByText("Risk 0")).toBeNull();
  });

  it("keeps the full graph (and no lens toolbar) below the threshold", () => {
    render(
      <MatrixGraph
        nodes={[
          mkNode({ id: "n1", node_type: "system", title: "LiDAR ingest" }),
          mkNode({ id: "n2", node_type: "risk", title: "Calibration slip" }),
        ]}
        edges={[]}
      />,
    );
    expect(screen.queryByTestId("matrix-lens-toolbar")).toBeNull();
    expect(screen.queryByTestId("matrix-lens-status")).toBeNull();
    expect(screen.queryByTestId("matrix-view-toggle")).toBeNull();
    expect(screen.getByText("LiDAR ingest")).toBeTruthy();
    expect(screen.getByText("Calibration slip")).toBeTruthy();
  });

  it("re-focuses the lens from the type-ahead search", () => {
    const { nodes, edges } = mkLensFixture();
    render(<MatrixGraph nodes={nodes} edges={edges} />);

    const input = screen.getByRole("combobox", { name: /search matrix nodes/i });
    fireEvent.change(input, { target: { value: "Distant" } });
    const results = screen.getByTestId("matrix-lens-search-results");
    // Results are grouped by node type.
    expect(within(results).getByRole("group", { name: "Systems" })).toBeTruthy();
    fireEvent.mouseDown(within(results).getByRole("option", { name: "Distant system" }));

    expect(screen.getByTestId("matrix-lens-status").textContent).toContain("Distant system");
    expect(screen.getByText("Distant system")).toBeTruthy();
    // The previous focus's neighborhood is gone (no path to the new focus).
    expect(screen.queryByText("Hub stakeholder")).toBeNull();
  });

  it("supports keyboard selection in the search listbox", () => {
    const { nodes, edges } = mkLensFixture();
    render(<MatrixGraph nodes={nodes} edges={edges} />);

    const input = screen.getByRole("combobox", { name: /search matrix nodes/i });
    fireEvent.change(input, { target: { value: "Quiet stakeholder" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(screen.getByTestId("matrix-lens-status").textContent).toContain("Quiet stakeholder");
  });

  it("expands the neighborhood when switching from 1 hop to 2 hops", () => {
    const { nodes, edges } = mkLensFixture();
    render(<MatrixGraph nodes={nodes} edges={edges} />);

    expect(screen.queryByText("Risk 0")).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "2 hops" }));
    // Risk 0 (via System 0) and Quiet stakeholder (also via System 0) join.
    expect(screen.getByText("Risk 0")).toBeTruthy();
    expect(screen.getByText("Quiet stakeholder")).toBeTruthy();
    expect(screen.getByTestId("matrix-lens-status").textContent).toContain(
      "showing 14 of 81 nodes",
    );
  });

  it("filters lens contents by node type via the chips, with count badges", () => {
    const { nodes, edges } = mkLensFixture();
    render(<MatrixGraph nodes={nodes} edges={edges} />);

    // Badges count the whole dataset, not just the visible subset.
    expect(screen.getByTestId("matrix-type-count-system").textContent).toBe("71");
    expect(screen.getByTestId("matrix-type-count-risk").textContent).toBe("8");
    expect(screen.getByTestId("matrix-type-count-stakeholder").textContent).toBe("2");

    expect(screen.getByText("Risk 1")).toBeTruthy();
    const riskChip = screen.getByTestId("matrix-type-filter-risk");
    expect(riskChip.getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(riskChip);
    expect(riskChip.getAttribute("aria-pressed")).toBe("false");
    expect(screen.queryByText("Risk 1")).toBeNull();
    // Other neighbors are unaffected.
    expect(screen.getByText("System 3")).toBeTruthy();
    fireEvent.click(riskChip);
    expect(screen.getByText("Risk 1")).toBeTruthy();
  });

  it("filters by node type in full (small-graph) mode too", () => {
    render(
      <MatrixGraph
        nodes={[
          mkNode({ id: "n1", node_type: "system", title: "LiDAR ingest" }),
          mkNode({ id: "n2", node_type: "risk", title: "Calibration slip" }),
        ]}
        edges={[mkEdge({ id: "e1", from_node_id: "n2", to_node_id: "n1" })]}
      />,
    );
    fireEvent.click(screen.getByTestId("matrix-type-filter-risk"));
    expect(screen.queryByText("Calibration slip")).toBeNull();
    expect(screen.getByText("LiDAR ingest")).toBeTruthy();
  });

  it("shows a recovery message instead of an empty canvas when every type is filtered out", () => {
    render(
      <MatrixGraph nodes={[mkNode({ id: "n1", node_type: "system", title: "Solo" })]} edges={[]} />,
    );
    fireEvent.click(screen.getByTestId("matrix-type-filter-system"));
    expect(screen.getByTestId("matrix-graph-filtered-empty")).toBeTruthy();
    expect(screen.queryByTestId("matrix-graph")).toBeNull();
  });

  it("opts into the full graph with a node-count warning, and back", () => {
    const { nodes, edges } = mkLensFixture();
    render(<MatrixGraph nodes={nodes} edges={edges} />);

    const toggle = screen.getByTestId("matrix-view-toggle");
    expect(toggle.textContent).toContain("Show full graph (81 nodes — may be slow)");
    fireEvent.click(toggle);
    // Full graph renders everything, including the unconnected node.
    expect(screen.getByText("Distant system")).toBeTruthy();
    expect(screen.getByText("System 69")).toBeTruthy();
    expect(screen.queryByTestId("matrix-lens-status")).toBeNull();

    expect(toggle.textContent).toContain("Back to lens view");
    fireEvent.click(toggle);
    expect(screen.queryByText("Distant system")).toBeNull();
    expect(screen.getByTestId("matrix-lens-status")).toBeTruthy();
  });

  it("respects a custom lensThreshold prop", () => {
    render(
      <MatrixGraph
        nodes={[
          mkNode({ id: "a", node_type: "system", title: "Alpha" }),
          mkNode({ id: "b", node_type: "system", title: "Beta" }),
        ]}
        edges={[]}
        lensThreshold={1}
      />,
    );
    expect(screen.getByTestId("matrix-lens-toolbar")).toBeTruthy();
    expect(screen.getByTestId("matrix-lens-status")).toBeTruthy();
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
