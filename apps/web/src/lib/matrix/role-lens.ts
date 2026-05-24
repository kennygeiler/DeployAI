import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

export type RoleLens = "all" | "fde" | "deployment_strategist" | "biz_dev";

export const ROLE_LENS_VALUES: readonly RoleLens[] = [
  "all",
  "fde",
  "deployment_strategist",
  "biz_dev",
] as const;

// Static node-type relevance per role. Provenance-based filtering (using the
// author/agent that produced each event) is a future slice — canonical events
// carry no author_role today.
const ROLE_NODE_TYPES: Record<Exclude<RoleLens, "all">, ReadonlySet<string>> = {
  deployment_strategist: new Set(["stakeholder", "decision", "commitment", "organization"]),
  fde: new Set(["system", "risk", "commitment"]),
  biz_dev: new Set(["opportunity", "organization", "stakeholder"]),
};

export function applyRoleLens(
  nodes: readonly MatrixNode[],
  edges: readonly MatrixEdge[],
  role: RoleLens,
): { nodes: MatrixNode[]; edges: MatrixEdge[] } {
  if (role === "all") {
    return { nodes: [...nodes], edges: [...edges] };
  }
  const allowed = ROLE_NODE_TYPES[role];
  const filteredNodes = nodes.filter((n) => allowed.has(n.node_type));
  const nodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = edges.filter(
    (e) => nodeIds.has(e.from_node_id) && nodeIds.has(e.to_node_id),
  );
  return { nodes: filteredNodes, edges: filteredEdges };
}
