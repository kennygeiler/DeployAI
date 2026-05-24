import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

export type BuiltinRoleLens = "all" | "fde" | "deployment_strategist" | "biz_dev";

// Wider than the baked-in trio — custom tenant roles are passed through as
// opaque strings. The lens function falls back to "all" semantics for any
// role not in the built-in mapping unless an explicit customRoles entry
// supplies a node-type list.
export type RoleLens = string;

export const ROLE_LENS_VALUES: readonly BuiltinRoleLens[] = [
  "all",
  "fde",
  "deployment_strategist",
  "biz_dev",
] as const;

export function isRoleLens(value: string): value is RoleLens {
  return typeof value === "string" && value.length > 0;
}

export function isBuiltinRoleLens(value: string): value is BuiltinRoleLens {
  return (ROLE_LENS_VALUES as readonly string[]).includes(value);
}

// Static node-type relevance per built-in role. Provenance-based filtering
// is a future slice — canonical events carry no author_role today.
const ROLE_NODE_TYPES: Record<Exclude<BuiltinRoleLens, "all">, ReadonlySet<string>> = {
  deployment_strategist: new Set(["stakeholder", "decision", "commitment", "organization"]),
  fde: new Set(["system", "risk", "commitment"]),
  biz_dev: new Set(["opportunity", "organization", "stakeholder"]),
};

export type CustomRoleLensEntry = {
  name: string;
  nodeTypes?: string[];
};

export function applyRoleLens(
  nodes: readonly MatrixNode[],
  edges: readonly MatrixEdge[],
  role: RoleLens,
  customRoles?: readonly CustomRoleLensEntry[],
): { nodes: MatrixNode[]; edges: MatrixEdge[] } {
  if (role === "all") {
    return { nodes: [...nodes], edges: [...edges] };
  }
  let allowed: ReadonlySet<string> | null = null;
  if (isBuiltinRoleLens(role) && role !== "all") {
    allowed = ROLE_NODE_TYPES[role];
  } else if (customRoles) {
    const entry = customRoles.find((c) => c.name === role);
    if (entry?.nodeTypes && entry.nodeTypes.length > 0) {
      allowed = new Set(entry.nodeTypes);
    }
  }
  if (allowed === null) {
    // Unknown / custom role with no mapping — show everything.
    return { nodes: [...nodes], edges: [...edges] };
  }
  const filteredNodes = nodes.filter((n) => allowed!.has(n.node_type));
  const nodeIds = new Set(filteredNodes.map((n) => n.id));
  const filteredEdges = edges.filter(
    (e) => nodeIds.has(e.from_node_id) && nodeIds.has(e.to_node_id),
  );
  return { nodes: filteredNodes, edges: filteredEdges };
}
