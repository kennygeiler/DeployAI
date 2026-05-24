import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

export type RoleLens = string;

export const ROLE_LENS_VALUES = ["all", "fde", "deployment_strategist", "biz_dev"] as const;

export type BuiltinRoleLens = (typeof ROLE_LENS_VALUES)[number];

export function isRoleLens(value: string): value is BuiltinRoleLens {
  return (ROLE_LENS_VALUES as readonly string[]).includes(value);
}

export type RoleLensCustomRole = {
  name: string;
  nodeTypes?: readonly string[];
};

// Static node-type relevance per role. Provenance-based filtering (using the
// author/agent that produced each event) is a future slice — canonical events
// carry no author_role today.
const ROLE_NODE_TYPES: Record<Exclude<BuiltinRoleLens, "all">, ReadonlySet<string>> = {
  deployment_strategist: new Set(["stakeholder", "decision", "commitment", "organization"]),
  fde: new Set(["system", "risk", "commitment"]),
  biz_dev: new Set(["opportunity", "organization", "stakeholder"]),
};

export function applyRoleLens(
  nodes: readonly MatrixNode[],
  edges: readonly MatrixEdge[],
  role: RoleLens,
  customRoles?: readonly RoleLensCustomRole[],
): { nodes: MatrixNode[]; edges: MatrixEdge[] } {
  if (role === "all") {
    return { nodes: [...nodes], edges: [...edges] };
  }
  let allowed: ReadonlySet<string> | null = null;
  if (role === "fde" || role === "deployment_strategist" || role === "biz_dev") {
    allowed = ROLE_NODE_TYPES[role];
  } else {
    const custom = customRoles?.find((r) => r.name === role);
    if (custom) {
      if (custom.nodeTypes) {
        allowed = new Set(custom.nodeTypes);
      } else {
        return { nodes: [...nodes], edges: [...edges] };
      }
    }
  }
  if (!allowed) {
    return { nodes: [...nodes], edges: [...edges] };
  }
  const filteredNodes = nodes.filter((n) => allowed.has(n.node_type));
  const nodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = edges.filter(
    (e) => nodeIds.has(e.from_node_id) && nodeIds.has(e.to_node_id),
  );
  return { nodes: filteredNodes, edges: filteredEdges };
}
