"use client";

import * as React from "react";

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

function formatOccurredAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function buildChildIndex(
  nodes: ProvenanceChainNode[],
  edges: ProvenanceChainEdge[],
): { byId: Map<string, ProvenanceChainNode>; childrenOf: Map<string, string[]> } {
  const byId = new Map<string, ProvenanceChainNode>();
  for (const n of nodes) byId.set(n.id, n);
  const childrenOf = new Map<string, string[]>();
  for (const e of edges) {
    const arr = childrenOf.get(e.toEventId) ?? [];
    arr.push(e.fromEventId);
    childrenOf.set(e.toEventId, arr);
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
            <span className="text-ink-600 text-xs">{formatOccurredAt(node.occurredAt)}</span>
            <span className="bg-ink-100 text-ink-800 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase">
              {node.sourceKind.replace(/_/g, " ")}
            </span>
            <span className="text-ink-500 text-[10px] uppercase">{node.actorKind}</span>
            {node.truncated ? (
              <span className="bg-warning-100 text-warning-900 rounded px-1.5 py-0.5 text-[10px] uppercase">
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
    () => buildChildIndex(chain.nodes, chain.edges),
    [chain.nodes, chain.edges],
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
