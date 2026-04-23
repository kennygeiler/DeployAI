import { corpus } from "./corpus.js";

export type SurfaceId = "digest" | "alert" | "phase" | "adjudication";

export type NodeView = {
  id: string;
  tenantId: string;
  phase: string;
  label: string;
  state: "active" | "overridden" | "tombstoned";
};

const tenantByIndex = corpus.tenants as string[];
const phases = corpus.phases as string[];

const base: Map<string, NodeView> = new Map(
  (corpus.nodes as { id: string; tenantIndex: number; phaseIndex: number; label: string }[]).map(
    (n) => [
      n.id,
      {
        id: n.id,
        tenantId: tenantByIndex[n.tenantIndex] ?? "",
        phase: phases[n.phaseIndex] ?? "",
        label: n.label,
        state: "active",
      },
    ],
  ),
);

/** In-memory simulation of canonical state (Epic 8 would be SQL). */
let stateVersion = 0;
const views: Map<string, NodeView> = new Map(base);

export function bumpStateVersion() {
  stateVersion += 1;
}

export function getStateVersion() {
  return stateVersion;
}

export function resolveNode(nodeId: string, surface: SurfaceId): NodeView | undefined {
  void surface;
  const v = views.get(nodeId);
  if (!v) {
    return undefined;
  }
  return { ...v };
}

export function getContextNeighborhood(nodeId: string) {
  const ctx = (corpus.contextByNodeId as Record<string, object>)[nodeId];
  if (!ctx) {
    return { stakeholderPeers: [], activeBlockers: [], recentEvents: [] };
  }
  return ctx as {
    stakeholderPeers: string[];
    activeBlockers: string[];
    recentEvents: string[];
  };
}

export function applyNodeState(nodeId: string, state: NodeView["state"]) {
  const cur = views.get(nodeId);
  if (!cur) {
    throw new Error(`unknown node ${nodeId}`);
  }
  views.set(nodeId, { ...cur, state });
  bumpStateVersion();
}
