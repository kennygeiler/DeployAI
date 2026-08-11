import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

/**
 * Wave 2.5 ticket U5 — "the graph is a lens, not a landing."
 *
 * Pure graph helpers behind the MatrixGraph lens view: adjacency/degree
 * computation, default-focus selection, and bounded neighborhood traversal.
 * Kept free of React so the selection and traversal rules are unit-testable
 * without mounting ReactFlow.
 */

/**
 * Above this many nodes the graph defaults to the focused lens view instead
 * of the full layout. 60 keeps small pilot engagements on the familiar
 * all-nodes view while BlueState-XL-scale matrices (866 nodes) never render
 * uninvited.
 */
export const LENS_NODE_THRESHOLD = 60;

/**
 * Hard cap on nodes shown in lens mode. Keeps the rendered element count
 * (nodes + column headers + induced edges) in the low hundreds even when a
 * hub node's 2-hop neighborhood is huge. Truncation keeps the
 * best-connected neighbors (see collectNeighborhood).
 */
export const LENS_NODE_CAP = 100;

export type LensHops = 1 | 2;

/** Undirected adjacency: node id -> ids of nodes sharing an edge with it. */
export type MatrixAdjacency = Map<string, Set<string>>;

export function buildAdjacency(edges: MatrixEdge[]): MatrixAdjacency {
  const adj: MatrixAdjacency = new Map();
  const link = (a: string, b: string) => {
    let set = adj.get(a);
    if (!set) {
      set = new Set();
      adj.set(a, set);
    }
    set.add(b);
  };
  for (const e of edges) {
    if (e.from_node_id === e.to_node_id) continue;
    link(e.from_node_id, e.to_node_id);
    link(e.to_node_id, e.from_node_id);
  }
  return adj;
}

export function degreeOf(adjacency: MatrixAdjacency, id: string): number {
  return adjacency.get(id)?.size ?? 0;
}

function updatedAtMs(n: MatrixNode): number {
  const t = Date.parse(n.updated_at);
  return Number.isNaN(t) ? 0 : t;
}

/**
 * Initial focus for the lens view: the highest-degree stakeholder — the DRM
 * question is "who matters on this deal", and the most-connected person is
 * the best default answer. Engagements with no stakeholders fall back to the
 * most-recently-updated node (what changed last is what the user came to
 * see). Ties break by recency then id so the pick is deterministic.
 */
export function pickDefaultFocus(
  nodes: MatrixNode[],
  adjacency: MatrixAdjacency,
): MatrixNode | null {
  if (nodes.length === 0) return null;
  const better = (a: MatrixNode, b: MatrixNode, primary: (n: MatrixNode) => number): MatrixNode => {
    const pa = primary(a);
    const pb = primary(b);
    if (pa !== pb) return pa > pb ? a : b;
    const ua = updatedAtMs(a);
    const ub = updatedAtMs(b);
    if (ua !== ub) return ua > ub ? a : b;
    return a.id < b.id ? a : b;
  };
  const stakeholders = nodes.filter((n) => n.node_type === "stakeholder");
  if (stakeholders.length > 0) {
    return stakeholders.reduce((best, n) => better(best, n, (m) => degreeOf(adjacency, m.id)));
  }
  return nodes.reduce((best, n) => better(best, n, updatedAtMs));
}

export type NeighborhoodResult = {
  /** Ids in the neighborhood (focus included), capped at `cap`. */
  ids: Set<string>;
  /** Total reachable within `hops` before the cap was applied. */
  reachable: number;
  truncated: boolean;
};

/**
 * Breadth-first neighborhood of `focusId` up to `hops` hops, restricted to
 * `allowedIds` (the type-filtered node set; the focus itself is always
 * allowed so toggling its type off cannot orphan the lens). When the
 * neighborhood exceeds `cap`, each frontier is sorted by degree (desc, id
 * asc for determinism) so the best-connected neighbors survive truncation.
 */
export function collectNeighborhood(
  focusId: string,
  adjacency: MatrixAdjacency,
  hops: LensHops,
  allowedIds: ReadonlySet<string>,
  cap: number = LENS_NODE_CAP,
): NeighborhoodResult {
  const ids = new Set<string>([focusId]);
  let reachable = 1;
  let truncated = false;
  let frontier = [focusId];
  for (let hop = 0; hop < hops; hop++) {
    const nextSeen = new Set<string>();
    for (const id of frontier) {
      for (const neighbor of adjacency.get(id) ?? []) {
        if (ids.has(neighbor) || nextSeen.has(neighbor)) continue;
        if (!allowedIds.has(neighbor)) continue;
        nextSeen.add(neighbor);
      }
    }
    reachable += nextSeen.size;
    const ranked = [...nextSeen].sort((a, b) => {
      const d = degreeOf(adjacency, b) - degreeOf(adjacency, a);
      return d !== 0 ? d : a < b ? -1 : 1;
    });
    const room = cap - ids.size;
    if (ranked.length > room) {
      truncated = true;
      ranked.length = Math.max(0, room);
    }
    for (const id of ranked) ids.add(id);
    frontier = ranked;
    if (ids.size >= cap) {
      // Anything the remaining hops would have added counts as truncated.
      truncated = truncated || hop < hops - 1;
      break;
    }
  }
  return { ids, reachable, truncated };
}

/** Node count per node_type, for the filter-chip badges. */
export function countNodesByType(nodes: MatrixNode[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const n of nodes) {
    counts.set(n.node_type, (counts.get(n.node_type) ?? 0) + 1);
  }
  return counts;
}
