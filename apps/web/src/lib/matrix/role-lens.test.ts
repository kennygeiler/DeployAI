import { describe, expect, it } from "vitest";

import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

import { applyRoleLens } from "./role-lens";

function mkNode(id: string, node_type: string, title = id): MatrixNode {
  return {
    id,
    engagement_id: "e1",
    node_type,
    title,
    identity_node_id: null,
    attributes: {},
    status: null,
    evidence_event_ids: [],
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
  };
}

function mkEdge(id: string, from_node_id: string, to_node_id: string): MatrixEdge {
  return {
    id,
    engagement_id: "e1",
    edge_type: "depends_on",
    from_node_id,
    to_node_id,
    attributes: {},
    evidence_event_ids: [],
    created_at: "2026-06-01T00:00:00Z",
    updated_at: "2026-06-01T00:00:00Z",
  };
}

const NODES: MatrixNode[] = [
  mkNode("sk1", "stakeholder"),
  mkNode("org1", "organization"),
  mkNode("sys1", "system"),
  mkNode("dec1", "decision"),
  mkNode("rsk1", "risk"),
  mkNode("cmt1", "commitment"),
  mkNode("opp1", "opportunity"),
];

const EDGES: MatrixEdge[] = [
  mkEdge("e-sk-org", "sk1", "org1"), // stakeholder → organization
  mkEdge("e-sys-rsk", "sys1", "rsk1"), // system → risk
  mkEdge("e-sys-org", "sys1", "org1"), // system → organization (cross-role)
  mkEdge("e-opp-org", "opp1", "org1"), // opportunity → organization
  mkEdge("e-cmt-dec", "cmt1", "dec1"), // commitment → decision
];

describe("applyRoleLens", () => {
  it('returns everything for "all"', () => {
    const r = applyRoleLens(NODES, EDGES, "all");
    expect(r.nodes).toHaveLength(NODES.length);
    expect(r.edges).toHaveLength(EDGES.length);
  });

  it("filters to deployment_strategist node types", () => {
    const r = applyRoleLens(NODES, EDGES, "deployment_strategist");
    const types = new Set(r.nodes.map((n) => n.node_type));
    expect(types).toEqual(new Set(["stakeholder", "decision", "commitment", "organization"]));
    // sk → org survives (both in lens); cmt → dec survives.
    const edgeIds = new Set(r.edges.map((e) => e.id));
    expect(edgeIds.has("e-sk-org")).toBe(true);
    expect(edgeIds.has("e-cmt-dec")).toBe(true);
    // sys → rsk and sys → org are dropped (system not in lens).
    expect(edgeIds.has("e-sys-rsk")).toBe(false);
    expect(edgeIds.has("e-sys-org")).toBe(false);
    // opp → org dropped (opportunity not in lens) — transitive filter.
    expect(edgeIds.has("e-opp-org")).toBe(false);
  });

  it("filters to fde node types", () => {
    const r = applyRoleLens(NODES, EDGES, "fde");
    const types = new Set(r.nodes.map((n) => n.node_type));
    expect(types).toEqual(new Set(["system", "risk", "commitment"]));
    const edgeIds = new Set(r.edges.map((e) => e.id));
    // Only sys → rsk has both endpoints in the lens.
    expect(edgeIds.has("e-sys-rsk")).toBe(true);
    expect(edgeIds.has("e-sys-org")).toBe(false);
    expect(edgeIds.has("e-cmt-dec")).toBe(false);
  });

  it("filters to biz_dev node types", () => {
    const r = applyRoleLens(NODES, EDGES, "biz_dev");
    const types = new Set(r.nodes.map((n) => n.node_type));
    expect(types).toEqual(new Set(["opportunity", "organization", "stakeholder"]));
    const edgeIds = new Set(r.edges.map((e) => e.id));
    expect(edgeIds.has("e-opp-org")).toBe(true);
    expect(edgeIds.has("e-sk-org")).toBe(true);
    // sys → org dropped: system not in lens even though org is.
    expect(edgeIds.has("e-sys-org")).toBe(false);
  });

  it("does not mutate the input arrays", () => {
    const nodesCopy = [...NODES];
    const edgesCopy = [...EDGES];
    applyRoleLens(NODES, EDGES, "fde");
    expect(NODES).toEqual(nodesCopy);
    expect(EDGES).toEqual(edgesCopy);
  });
});
