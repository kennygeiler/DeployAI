import { render, screen } from "@testing-library/react";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

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
});
