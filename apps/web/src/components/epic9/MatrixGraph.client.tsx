"use client";

import "@xyflow/react/dist/style.css";

import { Background, Controls, type Edge, MiniMap, type Node, ReactFlow } from "@xyflow/react";
import * as React from "react";

import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";

/**
 * Sprint 2 inc 1 — interactive graph view of the deployment matrix.
 *
 * Pairs with the existing table view in EngagementDetail. Same data,
 * different shape: pan / zoom / drag / inspect, with nodes coloured by
 * `node_type` and edges labelled by `edge_type`.
 *
 * Layout: columnar, deterministic. Columns = node types (left to right
 * in `BUILTIN_TYPE_ORDER` then any tenant-registered custom types);
 * rows within a column = the nodes of that type stacked vertically. No
 * force-directed sim — predictable layout is more readable than a
 * wiggly graph for a deployment-team UI, and it doesn't reflow when the
 * user drags.
 */

const BUILTIN_TYPE_ORDER = [
  "stakeholder",
  "organization",
  "system",
  "decision",
  "risk",
  "commitment",
  "opportunity",
] as const;

type BuiltinTypeKey = (typeof BUILTIN_TYPE_ORDER)[number];

const BUILTIN_TYPE_LABEL: Record<BuiltinTypeKey, string> = {
  stakeholder: "Stakeholders",
  organization: "Organizations",
  system: "Systems",
  decision: "Decisions",
  risk: "Risks",
  commitment: "Commitments",
  opportunity: "Opportunities",
};

const BUILTIN_TYPE_BG: Record<BuiltinTypeKey, string> = {
  stakeholder: "#fde68a",
  organization: "#bfdbfe",
  system: "#bbf7d0",
  decision: "#ddd6fe",
  risk: "#fecaca",
  commitment: "#fbcfe8",
  opportunity: "#a7f3d0",
};

const DEFAULT_CUSTOM_BG = "#e5e7eb";

const COLUMN_X = 240;
const ROW_Y = 90;
const COLUMN_HEADER_Y = -50;

export type CustomNodeTypeDescriptor = {
  name: string;
  label?: string | null;
  color?: string | null;
};

function buildTypeOrder(
  matrixNodes: MatrixNode[],
  customTypes: CustomNodeTypeDescriptor[],
): string[] {
  const order: string[] = [...BUILTIN_TYPE_ORDER];
  const seen = new Set(order);
  for (const c of customTypes) {
    if (!seen.has(c.name)) {
      order.push(c.name);
      seen.add(c.name);
    }
  }
  for (const n of matrixNodes) {
    if (!seen.has(n.node_type)) {
      order.push(n.node_type);
      seen.add(n.node_type);
    }
  }
  return order;
}

function buildLabelMap(customTypes: CustomNodeTypeDescriptor[]): Map<string, string> {
  const m = new Map<string, string>();
  for (const k of BUILTIN_TYPE_ORDER) {
    m.set(k, BUILTIN_TYPE_LABEL[k]);
  }
  for (const c of customTypes) {
    m.set(c.name, c.label ?? c.name);
  }
  return m;
}

function buildBgMap(customTypes: CustomNodeTypeDescriptor[]): Map<string, string> {
  const m = new Map<string, string>();
  for (const k of BUILTIN_TYPE_ORDER) {
    m.set(k, BUILTIN_TYPE_BG[k]);
  }
  for (const c of customTypes) {
    m.set(c.name, c.color ?? DEFAULT_CUSTOM_BG);
  }
  return m;
}

function buildNodes(
  matrixNodes: MatrixNode[],
  typeOrder: string[],
  labelMap: Map<string, string>,
  bgMap: Map<string, string>,
): Node[] {
  const out: Node[] = [];
  for (let col = 0; col < typeOrder.length; col++) {
    const t = typeOrder[col]!;
    const nodesOfType = matrixNodes.filter((n) => n.node_type === t);
    if (nodesOfType.length === 0) continue;
    out.push({
      id: `header-${t}`,
      position: { x: col * COLUMN_X, y: COLUMN_HEADER_Y },
      data: { label: labelMap.get(t) ?? t },
      draggable: false,
      selectable: false,
      style: {
        background: "transparent",
        border: "none",
        fontSize: 11,
        fontWeight: 600,
        textTransform: "uppercase",
        color: "#52525b",
        padding: 0,
      },
    });
    for (let row = 0; row < nodesOfType.length; row++) {
      const n = nodesOfType[row]!;
      out.push({
        id: n.id,
        position: { x: col * COLUMN_X, y: row * ROW_Y },
        data: { label: n.title },
        style: {
          background: bgMap.get(t) ?? DEFAULT_CUSTOM_BG,
          border: "1px solid #71717a",
          borderRadius: 8,
          padding: 8,
          fontSize: 12,
          width: 200,
        },
      });
    }
  }
  return out;
}

function buildEdges(matrixEdges: MatrixEdge[]): Edge[] {
  return matrixEdges.map((e) => ({
    id: e.id,
    source: e.from_node_id,
    target: e.to_node_id,
    label: e.edge_type.replace(/_/g, " "),
    labelStyle: { fontSize: 10, fill: "#52525b" },
    labelBgStyle: { fill: "#fafafa" },
    style: { stroke: "#a1a1aa", strokeWidth: 1.5 },
  }));
}

export function MatrixGraph({
  nodes,
  edges,
  customTypes,
  onNodeClick,
}: {
  nodes: MatrixNode[];
  edges: MatrixEdge[];
  customTypes?: CustomNodeTypeDescriptor[];
  onNodeClick?: (node: MatrixNode) => void;
}) {
  const custom = React.useMemo(() => customTypes ?? [], [customTypes]);
  const typeOrder = React.useMemo(() => buildTypeOrder(nodes, custom), [nodes, custom]);
  const labelMap = React.useMemo(() => buildLabelMap(custom), [custom]);
  const bgMap = React.useMemo(() => buildBgMap(custom), [custom]);
  const rfNodes = React.useMemo(
    () => buildNodes(nodes, typeOrder, labelMap, bgMap),
    [nodes, typeOrder, labelMap, bgMap],
  );
  const rfEdges = React.useMemo(() => buildEdges(edges), [edges]);
  const nodesById = React.useMemo(() => {
    const m = new Map<string, MatrixNode>();
    for (const n of nodes) m.set(n.id, n);
    return m;
  }, [nodes]);

  const handleNodeClick = React.useCallback(
    (_e: React.MouseEvent, n: Node) => {
      if (!onNodeClick) return;
      if (n.id.startsWith("header-")) return;
      const matched = nodesById.get(n.id);
      if (matched) {
        onNodeClick(matched);
      }
    },
    [onNodeClick, nodesById],
  );

  if (nodes.length === 0) {
    return (
      <p className="text-ink-600 text-sm">
        No matrix entities yet — the graph fills in as nodes are added.
      </p>
    );
  }

  return (
    <div
      data-testid="matrix-graph"
      className="border-border h-[600px] w-full rounded-lg border"
      aria-label="Deployment matrix graph"
      role="figure"
    >
      <ReactFlow
        nodes={rfNodes}
        edges={rfEdges}
        fitView
        proOptions={{ hideAttribution: true }}
        nodesConnectable={false}
        edgesFocusable={false}
        defaultEdgeOptions={{ type: "smoothstep" }}
        onNodeClick={handleNodeClick}
      >
        <Background gap={20} />
        <Controls position="bottom-right" showInteractive={false} />
        <MiniMap pannable zoomable position="top-right" />
      </ReactFlow>
    </div>
  );
}
