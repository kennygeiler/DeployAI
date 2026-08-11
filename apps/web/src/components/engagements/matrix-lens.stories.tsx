import type { Meta, StoryObj } from "@storybook/nextjs-vite";

import { MatrixGraph } from "@/components/epic9/MatrixGraph.client";
import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

/**
 * Engagements / Matrix lens (ticket U5) — above `LENS_NODE_THRESHOLD` nodes
 * the matrix graph opens as a lens: the highest-degree stakeholder's
 * neighborhood, with search-to-focus, a 1/2-hop toggle, and type filter
 * chips. The full layout stays available behind an explicit opt-in.
 *
 * The fixture below generates a deterministic 200-node engagement so the
 * lens behavior is reviewable without seeding a backend.
 */

const TYPE_PLAN: Array<{ type: string; count: number; title: (i: number) => string }> = [
  { type: "stakeholder", count: 24, title: (i) => `Stakeholder ${i} — Ops lead` },
  { type: "organization", count: 10, title: (i) => `Org ${i} — Agency` },
  { type: "system", count: 60, title: (i) => `System ${i} — Pipeline` },
  { type: "decision", count: 30, title: (i) => `Decision ${i} — Rollout gate` },
  { type: "risk", count: 40, title: (i) => `Risk ${i} — Slippage` },
  { type: "commitment", count: 26, title: (i) => `Commitment ${i} — Deliverable` },
  { type: "opportunity", count: 10, title: (i) => `Opportunity ${i} — Expansion` },
];

// Small deterministic PRNG so the story renders identically on every load.
function lcg(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
}

function generateFixture(nodeTarget = 200): { nodes: MatrixNode[]; edges: MatrixEdge[] } {
  const rand = lcg(20260811);
  const nodes: MatrixNode[] = [];
  for (const plan of TYPE_PLAN) {
    for (let i = 0; i < plan.count && nodes.length < nodeTarget; i++) {
      const day = 1 + Math.floor(rand() * 28);
      nodes.push({
        id: `${plan.type}-${i}`,
        engagement_id: "story-engagement",
        node_type: plan.type,
        title: plan.title(i),
        identity_node_id: null,
        attributes: {},
        status: null,
        evidence_event_ids: [],
        created_at: "2026-05-01T00:00:00Z",
        updated_at: `2026-07-${String(day).padStart(2, "0")}T00:00:00Z`,
      });
    }
  }
  const edges: MatrixEdge[] = [];
  const pick = (type: string) => {
    const ofType = nodes.filter((n) => n.node_type === type);
    return ofType[Math.floor(rand() * ofType.length)]!;
  };
  const addEdge = (edgeType: string, from: MatrixNode, to: MatrixNode) => {
    if (from.id === to.id) return;
    edges.push({
      id: `edge-${edges.length}`,
      engagement_id: "story-engagement",
      edge_type: edgeType,
      from_node_id: from.id,
      to_node_id: to.id,
      attributes: {},
      evidence_event_ids: [],
      created_at: "2026-05-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
    });
  };
  // A hub stakeholder so the default focus has an interesting neighborhood.
  const hub = nodes.find((n) => n.id === "stakeholder-0")!;
  for (let i = 0; i < 14; i++) addEdge("sponsors", hub, pick("system"));
  for (let i = 0; i < 4; i++) addEdge("owns", hub, pick("decision"));
  // Background structure across the rest of the graph.
  for (let i = 0; i < 40; i++) addEdge("sponsors", pick("stakeholder"), pick("system"));
  for (let i = 0; i < 30; i++) addEdge("threatens", pick("risk"), pick("system"));
  for (let i = 0; i < 25; i++) addEdge("depends_on", pick("system"), pick("system"));
  for (let i = 0; i < 20; i++) addEdge("affects", pick("decision"), pick("system"));
  for (let i = 0; i < 20; i++) addEdge("owed_by", pick("commitment"), pick("stakeholder"));
  for (let i = 0; i < 15; i++) addEdge("belongs_to", pick("stakeholder"), pick("organization"));
  for (let i = 0; i < 10; i++) addEdge("enables", pick("system"), pick("opportunity"));
  return { nodes, edges };
}

const large = generateFixture(200);
const small = {
  nodes: large.nodes.filter((n) => /-(0|1|2)$/.test(n.id)),
  edges: [] as MatrixEdge[],
};

const meta = {
  title: "Engagements/MatrixLens",
  component: MatrixGraph,
  tags: ["autodocs"],
  parameters: { layout: "padded" },
} satisfies Meta<typeof MatrixGraph>;

export default meta;
type Story = StoryObj<typeof meta>;

/** 200 generated nodes: opens in lens mode on the hub stakeholder. */
export const LensOn200Nodes: Story = {
  args: { nodes: large.nodes, edges: large.edges },
};

/** Below the threshold the classic full columnar layout renders directly. */
export const SmallGraphFullView: Story = {
  args: { nodes: small.nodes, edges: small.edges },
};

/**
 * Threshold raised above the fixture size — the 200-node full layout the
 * lens protects users from by default (also what "Show full graph" yields).
 */
export const FullGraphForced: Story = {
  args: { nodes: large.nodes, edges: large.edges, lensThreshold: 1000 },
};
