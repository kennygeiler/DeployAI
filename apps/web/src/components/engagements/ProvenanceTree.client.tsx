"use client";

import * as React from "react";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import { Button } from "@/components/ui/button";

export type ProvenanceChainNode = {
  id: string;
  occurredAt: string;
  sourceKind: string;
  summary: string;
  actorKind: string;
  depth: number;
  truncated: boolean;
};

export type ProvenanceChainEdge = {
  fromEventId: string;
  toEventId: string;
};

export type ProvenanceChain = {
  rootEventId: string;
  nodes: ProvenanceChainNode[];
  edges: ProvenanceChainEdge[];
  truncatedAtDepth: number | null;
  truncatedNodeCount: number | null;
};

function buildChildIndex(
  nodes: ProvenanceChainNode[],
  edges: ProvenanceChainEdge[],
  rootEventId: string,
): { byId: Map<string, ProvenanceChainNode>; childrenOf: Map<string, string[]> } {
  const byId = new Map<string, ProvenanceChainNode>();
  for (const n of nodes) byId.set(n.id, n);

  // The chain endpoint returns edges oriented root -> upstream cause
  // (fromEventId is the root/nearer event). Rather than trusting either
  // orientation, treat edges as undirected and derive parent -> children by
  // BFS from the root, so the tree renders correctly even if the API's edge
  // direction changes again.
  const adjacency = new Map<string, string[]>();
  const link = (a: string, b: string) => {
    const arr = adjacency.get(a) ?? [];
    arr.push(b);
    adjacency.set(a, arr);
  };
  for (const e of edges) {
    link(e.fromEventId, e.toEventId);
    link(e.toEventId, e.fromEventId);
  }

  const childrenOf = new Map<string, string[]>();
  const seen = new Set<string>([rootEventId]);
  const queue = [rootEventId];
  while (queue.length > 0) {
    const current = queue.shift() as string;
    for (const neighbor of adjacency.get(current) ?? []) {
      if (seen.has(neighbor)) continue;
      seen.add(neighbor);
      const arr = childrenOf.get(current) ?? [];
      arr.push(neighbor);
      childrenOf.set(current, arr);
      queue.push(neighbor);
    }
  }
  return { byId, childrenOf };
}

function TreeNode({
  node,
  childrenOf,
  byId,
  visited,
  defaultExpanded,
}: {
  node: ProvenanceChainNode;
  childrenOf: Map<string, string[]>;
  byId: Map<string, ProvenanceChainNode>;
  visited: ReadonlySet<string>;
  defaultExpanded: boolean;
}) {
  const childIds = childrenOf.get(node.id) ?? [];
  const hasChildren = childIds.length > 0;
  const [expanded, setExpanded] = React.useState(defaultExpanded);
  const labelId = `prov-node-${node.id}-label`;
  return (
    <li className="space-y-1" aria-labelledby={labelId}>
      <div className="flex items-start gap-2">
        {hasChildren ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-xs"
            aria-expanded={expanded}
            aria-controls={`prov-children-${node.id}`}
            aria-label={expanded ? "Collapse upstream events" : "Expand upstream events"}
            onClick={() => setExpanded((v) => !v)}
            className="mt-0.5"
          >
            <span aria-hidden="true">{expanded ? "▾" : "▸"}</span>
          </Button>
        ) : (
          <span aria-hidden="true" className="mt-0.5 inline-block h-6 w-6 shrink-0" />
        )}
        <div className="min-w-0 flex-1 space-y-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <TimestampLabel value={node.occurredAt} />
            <span className="bg-ink-100 text-ink-800 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase">
              {node.sourceKind.replace(/_/g, " ")}
            </span>
            <span className="text-ink-500 text-[10px] uppercase">{node.actorKind}</span>
            {node.truncated ? (
              <span className="bg-orange-tint text-orange-ink rounded px-1.5 py-0.5 text-[10px] uppercase">
                truncated
              </span>
            ) : null}
          </div>
          <p id={labelId} className="text-ink-800 whitespace-pre-line">
            {node.summary}
          </p>
        </div>
      </div>
      {hasChildren && expanded ? (
        <ul id={`prov-children-${node.id}`} className="border-border ml-3 space-y-2 border-l pl-3">
          {childIds.map((cid) => {
            const child = byId.get(cid);
            if (!child) return null;
            if (visited.has(cid)) {
              return (
                <li key={cid} className="text-ink-500 text-xs italic">
                  ↺ cycle to event {cid.slice(0, 8)}
                </li>
              );
            }
            const nextVisited = new Set(visited);
            nextVisited.add(cid);
            return (
              <TreeNode
                key={cid}
                node={child}
                childrenOf={childrenOf}
                byId={byId}
                visited={nextVisited}
                defaultExpanded={defaultExpanded}
              />
            );
          })}
        </ul>
      ) : null}
    </li>
  );
}

export function ProvenanceTree({
  chain,
  defaultExpanded = true,
}: {
  chain: ProvenanceChain;
  defaultExpanded?: boolean;
}) {
  const { byId, childrenOf } = React.useMemo(
    () => buildChildIndex(chain.nodes, chain.edges, chain.rootEventId),
    [chain.nodes, chain.edges, chain.rootEventId],
  );
  const root = byId.get(chain.rootEventId);
  if (!root) {
    return <p className="text-ink-600 text-sm">No provenance chain available.</p>;
  }
  const initialVisited = new Set<string>([chain.rootEventId]);
  return (
    <div data-testid="provenance-tree" className="space-y-2 text-sm">
      <ul className="space-y-2" aria-label="Causal chain">
        <TreeNode
          node={root}
          childrenOf={childrenOf}
          byId={byId}
          visited={initialVisited}
          defaultExpanded={defaultExpanded}
        />
      </ul>
      {chain.truncatedAtDepth !== null || chain.truncatedNodeCount !== null ? (
        <p className="text-ink-500 text-xs">
          Chain truncated
          {chain.truncatedAtDepth !== null ? ` at depth ${chain.truncatedAtDepth}` : ""}
          {chain.truncatedNodeCount !== null
            ? ` (${chain.truncatedNodeCount} additional event${
                chain.truncatedNodeCount === 1 ? "" : "s"
              } hidden)`
            : ""}
          .
        </p>
      ) : null}
    </div>
  );
}
