import { describe, expect, it } from "vitest";

import {
  buildAdjacency,
  collectNeighborhood,
  countNodesByType,
  degreeOf,
  LENS_NODE_CAP,
  LENS_NODE_THRESHOLD,
  pickDefaultFocus,
} from "@/components/engagements/matrix-lens";
import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

function mkNode(overrides: Partial<MatrixNode> = {}): MatrixNode {
  return {
    id: "n1",
    engagement_id: "e1",
    node_type: "system",
    title: "Node",
    identity_node_id: null,
    attributes: {},
    status: null,
    evidence_event_ids: [],
    created_at: "2026-05-09T00:00:00Z",
    updated_at: "2026-05-09T00:00:00Z",
    ...overrides,
  };
}

function mkEdge(from: string, to: string, id = `${from}->${to}`): MatrixEdge {
  return {
    id,
    engagement_id: "e1",
    edge_type: "affects",
    from_node_id: from,
    to_node_id: to,
    attributes: {},
    evidence_event_ids: [],
    created_at: "2026-05-09T00:00:00Z",
    updated_at: "2026-05-09T00:00:00Z",
  };
}

describe("buildAdjacency", () => {
  it("is undirected and ignores self-loops", () => {
    const adj = buildAdjacency([mkEdge("a", "b"), mkEdge("c", "c")]);
    expect(adj.get("a")?.has("b")).toBe(true);
    expect(adj.get("b")?.has("a")).toBe(true);
    expect(adj.get("c")).toBeUndefined();
  });

  it("counts parallel edges between the same pair once for degree purposes", () => {
    const adj = buildAdjacency([mkEdge("a", "b", "e1"), mkEdge("b", "a", "e2")]);
    expect(degreeOf(adj, "a")).toBe(1);
  });
});

describe("pickDefaultFocus", () => {
  it("returns null for an empty matrix", () => {
    expect(pickDefaultFocus([], new Map())).toBeNull();
  });

  it("picks the highest-degree stakeholder when stakeholders exist", () => {
    const nodes = [
      mkNode({ id: "s1", node_type: "stakeholder" }),
      mkNode({ id: "s2", node_type: "stakeholder" }),
      mkNode({ id: "x1" }),
      mkNode({ id: "x2" }),
    ];
    const adj = buildAdjacency([mkEdge("s2", "x1"), mkEdge("s2", "x2"), mkEdge("s1", "x1")]);
    expect(pickDefaultFocus(nodes, adj)?.id).toBe("s2");
  });

  it("prefers a low-degree stakeholder over a high-degree non-stakeholder", () => {
    const nodes = [mkNode({ id: "s1", node_type: "stakeholder" }), mkNode({ id: "hub" })];
    const adj = buildAdjacency([mkEdge("hub", "a"), mkEdge("hub", "b"), mkEdge("hub", "c")]);
    expect(pickDefaultFocus(nodes, adj)?.id).toBe("s1");
  });

  it("breaks stakeholder degree ties by recency, then id", () => {
    const nodes = [
      mkNode({ id: "s1", node_type: "stakeholder", updated_at: "2026-05-01T00:00:00Z" }),
      mkNode({ id: "s2", node_type: "stakeholder", updated_at: "2026-05-02T00:00:00Z" }),
      mkNode({ id: "s3", node_type: "stakeholder", updated_at: "2026-05-02T00:00:00Z" }),
    ];
    expect(pickDefaultFocus(nodes, new Map())?.id).toBe("s2");
  });

  it("falls back to the most-recently-updated node when there are no stakeholders", () => {
    const nodes = [
      mkNode({ id: "old", updated_at: "2026-01-01T00:00:00Z" }),
      mkNode({ id: "new", updated_at: "2026-06-01T00:00:00Z" }),
    ];
    expect(pickDefaultFocus(nodes, new Map())?.id).toBe("new");
  });
});

describe("collectNeighborhood", () => {
  // Chain: a - b - c - d, plus a - e.
  const chain = buildAdjacency([
    mkEdge("a", "b"),
    mkEdge("b", "c"),
    mkEdge("c", "d"),
    mkEdge("a", "e"),
  ]);
  const all = new Set(["a", "b", "c", "d", "e"]);

  it("collects the 1-hop neighborhood including the focus", () => {
    const r = collectNeighborhood("a", chain, 1, all);
    expect([...r.ids].sort()).toEqual(["a", "b", "e"]);
    expect(r.truncated).toBe(false);
  });

  it("collects the 2-hop neighborhood", () => {
    const r = collectNeighborhood("a", chain, 2, all);
    expect([...r.ids].sort()).toEqual(["a", "b", "c", "e"]);
  });

  it("does not traverse through nodes excluded by the type filter", () => {
    const allowed = new Set(["a", "c", "d", "e"]); // b filtered out
    const r = collectNeighborhood("a", chain, 2, allowed);
    // c is only reachable via b, so it stays hidden.
    expect([...r.ids].sort()).toEqual(["a", "e"]);
  });

  it("caps the neighborhood and keeps the best-connected neighbors", () => {
    // Star: focus linked to leaf0..leaf4; leaf0 is also a hub (extra edges).
    const edges = [
      ...Array.from({ length: 5 }, (_, i) => mkEdge("focus", `leaf${i}`)),
      mkEdge("leaf0", "z1"),
      mkEdge("leaf0", "z2"),
    ];
    const adj = buildAdjacency(edges);
    const allowed = new Set(["focus", "leaf0", "leaf1", "leaf2", "leaf3", "leaf4", "z1", "z2"]);
    const r = collectNeighborhood("focus", adj, 1, allowed, 3);
    expect(r.ids.size).toBe(3);
    expect(r.ids.has("focus")).toBe(true);
    expect(r.ids.has("leaf0")).toBe(true); // highest degree survives the cap
    expect(r.truncated).toBe(true);
    expect(r.reachable).toBe(6);
  });

  it("handles a focus with no edges", () => {
    const r = collectNeighborhood("lonely", chain, 2, new Set(["lonely"]));
    expect([...r.ids]).toEqual(["lonely"]);
    expect(r.reachable).toBe(1);
  });
});

describe("countNodesByType", () => {
  it("tallies node counts per type", () => {
    const counts = countNodesByType([
      mkNode({ id: "1", node_type: "system" }),
      mkNode({ id: "2", node_type: "system" }),
      mkNode({ id: "3", node_type: "risk" }),
    ]);
    expect(counts.get("system")).toBe(2);
    expect(counts.get("risk")).toBe(1);
    expect(counts.get("stakeholder")).toBeUndefined();
  });
});

describe("lens constants", () => {
  it("keeps the lens budget well under the XL node count", () => {
    expect(LENS_NODE_THRESHOLD).toBeLessThan(LENS_NODE_CAP);
    expect(LENS_NODE_CAP).toBeLessThanOrEqual(150);
  });
});
