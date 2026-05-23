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
 * in `TYPE_ORDER`); rows within a column = the nodes of that type
 * stacked vertically. No force-directed sim — predictable layout is
 * more readable than a wiggly graph for a deployment-team UI, and it
 * doesn't reflow when the user drags.
 *
 * Data contract is exactly the existing `MatrixNode` + `MatrixEdge`
 * rows shipped by the engagement-detail BFF — we add no new fields.
 */

const TYPE_ORDER = [
  "stakeholder",
  "organization",
  "system",
  "decision",
  "risk",
  "commitment",
  "opportunity",
] as const;

type NodeTypeKey = (typeof TYPE_ORDER)[number];

const TYPE_LABEL: Record<NodeTypeKey, string> = {
  stakeholder: "Stakeholders",
  organization: "Organizations",
  system: "Systems",
  decision: "Decisions",
  risk: "Risks",
  commitment: "Commitments",
  opportunity: "Opportunities",
};

// Subtle background colour per node type. Tailwind-resolved so the
// graph reads on both light and dark surfaces.
const TYPE_BG: Record<NodeTypeKey, string> = {
  stakeholder: "#fde68a", // amber-200
  organization: "#bfdbfe", // blue-200
  system: "#bbf7d0", // green-200
  decision: "#ddd6fe", // violet-200
  risk: "#fecaca", // red-200
  commitment: "#fbcfe8", // pink-200
  opportunity: "#a7f3d0", // emerald-200
};

const COLUMN_X = 240;
const ROW_Y = 90;
const COLUMN_HEADER_Y = -50;

function buildNodes(matrixNodes: MatrixNode[]): Node[] {
  const out: Node[] = [];
  for (let col = 0; col < TYPE_ORDER.length; col++) {
    const t = TYPE_ORDER[col]!;
    const nodesOfType = matrixNodes.filter((n) => n.node_type === t);
    if (nodesOfType.length === 0) continue;
    // Column header — a non-interactive marker node.
    out.push({
      id: `header-${t}`,
      position: { x: col * COLUMN_X, y: COLUMN_HEADER_Y },
      data: { label: TYPE_LABEL[t] },
      draggable: false,
      selectable: false,
      style: {
        background: "transparent",
        border: "none",
        fontSize: 11,
        fontWeight: 600,
        textTransform: "uppercase",
        color: "#52525b", // ink-600-ish
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
          background: TYPE_BG[t],
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

export function MatrixGraph({ nodes, edges }: { nodes: MatrixNode[]; edges: MatrixEdge[] }) {
  const rfNodes = React.useMemo(() => buildNodes(nodes), [nodes]);
  const rfEdges = React.useMemo(() => buildEdges(edges), [edges]);

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
      >
        <Background gap={20} />
        <Controls position="bottom-right" showInteractive={false} />
        <MiniMap pannable zoomable position="top-right" />
      </ReactFlow>
    </div>
  );
}
