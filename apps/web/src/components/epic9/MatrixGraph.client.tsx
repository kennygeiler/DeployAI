"use client";

import "@xyflow/react/dist/style.css";

import { Background, Controls, type Edge, MiniMap, type Node, ReactFlow } from "@xyflow/react";
import { usePathname, useSearchParams } from "next/navigation";
import * as React from "react";

import { z } from "zod";

import { MatrixTimeSlider } from "@/components/engagements/MatrixTimeSlider.client";
import { MatrixLegend } from "@/components/epic9/MatrixLegend.client";
import type { MatrixEdge, MatrixNode } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import { zMatrixSnapshot } from "@/lib/internal/matrix-snapshot-cp";

const zSnapshotBffResponse = z.object({ snapshot: zMatrixSnapshot });

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

export const BUILTIN_TYPE_ORDER = [
  "stakeholder",
  "organization",
  "system",
  "decision",
  "risk",
  "commitment",
  "opportunity",
] as const;

export type BuiltinTypeKey = (typeof BUILTIN_TYPE_ORDER)[number];

export const BUILTIN_TYPE_LABEL: Record<BuiltinTypeKey, string> = {
  stakeholder: "Stakeholders",
  organization: "Organizations",
  system: "Systems",
  decision: "Decisions",
  risk: "Risks",
  commitment: "Commitments",
  opportunity: "Opportunities",
};

// Okabe-Ito colorblind-safe palette (tinted for fill use). The original
// red/green pairing (system #bbf7d0 vs risk #fecaca) collapsed under
// deuteranopia + protanopia. These eight base hues stay distinguishable for
// the three common CVD types; we use seven for the built-in node types.
export const BUILTIN_TYPE_BG: Record<BuiltinTypeKey, string> = {
  stakeholder: "#ffe9bf", // Okabe-Ito orange (#E69F00) tinted
  organization: "#cfe8fb", // Okabe-Ito sky blue (#56B4E9) tinted
  system: "#c9e9de", // Okabe-Ito bluish green (#009E73) tinted
  decision: "#e0d6ea", // Okabe-Ito reddish purple (#CC79A7) tinted
  risk: "#f8d5bb", // Okabe-Ito vermillion (#D55E00) tinted
  commitment: "#fbf6c4", // Okabe-Ito yellow (#F0E442) tinted
  opportunity: "#bfd3eb", // Okabe-Ito blue (#0072B2) tinted
};

export const BUILTIN_TYPE_COLOR_NAME: Record<BuiltinTypeKey, string> = {
  stakeholder: "Orange",
  organization: "Sky blue",
  system: "Bluish green",
  decision: "Reddish purple",
  risk: "Vermillion",
  commitment: "Yellow",
  opportunity: "Blue",
};

const DEFAULT_CUSTOM_BG = "#e5e7eb";

// Edge styles by edge_type. Hex codes chosen from the existing Tailwind
// palette so the legend swatches and graph strokes match across the app.
// Dashed strokes give a second non-color cue for the "directional debt"
// edges (`owed_by` / `owed_to`) — color alone is insufficient for CVD.
type EdgeStyleEntry = {
  stroke: string;
  strokeDasharray?: string;
  colorName: string;
};

export const EDGE_STYLE: Record<string, EdgeStyleEntry> = {
  sponsors: { stroke: "#2563eb", colorName: "Blue" }, // tailwind blue-600
  owns: { stroke: "#16a34a", colorName: "Green" }, // tailwind green-600
  depends_on: { stroke: "#d97706", colorName: "Amber" }, // tailwind amber-600
  blocks: { stroke: "#dc2626", colorName: "Red" }, // tailwind red-600
  affects: { stroke: "#6b7280", colorName: "Gray" }, // tailwind gray-500
  belongs_to: { stroke: "#0d9488", colorName: "Teal" }, // tailwind teal-600
  threatens: { stroke: "#c026d3", colorName: "Fuchsia" }, // tailwind fuchsia-600
  owed_by: { stroke: "#7c3aed", strokeDasharray: "6 4", colorName: "Violet (dashed)" }, // tailwind violet-600
  owed_to: { stroke: "#db2777", strokeDasharray: "6 4", colorName: "Pink (dashed)" }, // tailwind pink-600
  enables: { stroke: "#0891b2", colorName: "Cyan" }, // tailwind cyan-600
};

const DEFAULT_EDGE_STROKE = "#a1a1aa";

const COLUMN_X = 240;
const ROW_Y = 90;
const COLUMN_HEADER_Y = -50;

const STALE_THRESHOLD_MS = 24 * 60 * 60 * 1000;

function isSnapshotStale(capturedAt: string, liveNodes: MatrixNode[]): boolean {
  const captured = Date.parse(capturedAt);
  if (Number.isNaN(captured)) return false;
  let latest = 0;
  for (const n of liveNodes) {
    const t = Date.parse(n.updated_at);
    if (!Number.isNaN(t) && t > latest) latest = t;
  }
  if (latest === 0) return false;
  return captured < latest - STALE_THRESHOLD_MS;
}

function formatSnapshotDate(capturedAt: string): string {
  const t = Date.parse(capturedAt);
  if (Number.isNaN(t)) return capturedAt;
  return new Date(t).toISOString().slice(0, 10);
}

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

// Pathnames the matrix is rendered on are scoped under /engagements/<id>. When
// MatrixGraph isn't passed an explicit engagementId we read it from the path so
// the time slider can wire to the snapshot BFF without callers being updated.
const ENGAGEMENT_PATH_RE = /^\/engagements\/([^/]+)(?:\/|$)/;

function engagementIdFromPathname(pathname: string | null): string | undefined {
  if (!pathname) return undefined;
  const m = ENGAGEMENT_PATH_RE.exec(pathname);
  const raw = m?.[1];
  if (!raw) return undefined;
  try {
    return decodeURIComponent(raw);
  } catch {
    return undefined;
  }
}

function buildEdges(matrixEdges: MatrixEdge[]): Edge[] {
  return matrixEdges.map((e) => {
    const styleEntry = EDGE_STYLE[e.edge_type];
    const stroke = styleEntry?.stroke ?? DEFAULT_EDGE_STROKE;
    const dash = styleEntry?.strokeDasharray;
    return {
      id: e.id,
      source: e.from_node_id,
      target: e.to_node_id,
      label: e.edge_type.replace(/_/g, " "),
      labelStyle: { fontSize: 10, fill: "#52525b" },
      labelBgStyle: { fill: "#fafafa" },
      style: dash
        ? { stroke, strokeWidth: 1.5, strokeDasharray: dash }
        : { stroke, strokeWidth: 1.5 },
    };
  });
}

type FetchedSnapshot =
  | { kind: "loading" }
  | { kind: "ready"; nodes: MatrixNode[]; edges: MatrixEdge[]; capturedAt: string }
  | { kind: "missing"; at: string }
  | { kind: "error"; message: string };

type SnapshotState = { kind: "idle" } | FetchedSnapshot;

function useMatrixSnapshot(engagementId: string | undefined, at: string | null): SnapshotState {
  type Entry = { key: string; result: FetchedSnapshot };
  const [entry, setEntry] = React.useState<Entry | null>(null);
  const requestKey = engagementId && at ? `${engagementId}|${at}` : null;
  React.useEffect(() => {
    if (!engagementId || !at || !requestKey) {
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/matrix-snapshot?at=${encodeURIComponent(at)}`,
          { cache: "no-store" },
        );
        if (cancelled) return;
        if (r.status === 404) {
          setEntry({ key: requestKey, result: { kind: "missing", at } });
          return;
        }
        if (!r.ok) {
          setEntry({
            key: requestKey,
            result: { kind: "error", message: await readStrategistBffErrorDescription(r) },
          });
          return;
        }
        const raw: unknown = await r.json();
        const parsed = zSnapshotBffResponse.safeParse(raw);
        if (!parsed.success) {
          setEntry({
            key: requestKey,
            result: { kind: "error", message: "Malformed snapshot response." },
          });
          return;
        }
        setEntry({
          key: requestKey,
          result: {
            kind: "ready",
            nodes: parsed.data.snapshot.nodes as MatrixNode[],
            edges: parsed.data.snapshot.edges as MatrixEdge[],
            capturedAt: parsed.data.snapshot.captured_at,
          },
        });
      } catch (e) {
        if (cancelled) return;
        setEntry({
          key: requestKey,
          result: {
            kind: "error",
            message: e instanceof Error ? e.message : "Could not load snapshot.",
          },
        });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [engagementId, at, requestKey]);
  if (!requestKey) {
    return { kind: "idle" };
  }
  if (entry && entry.key === requestKey) {
    return entry.result;
  }
  return { kind: "loading" };
}

export function MatrixGraph({
  nodes,
  edges,
  customTypes,
  engagementId,
  onNodeClick,
}: {
  nodes: MatrixNode[];
  edges: MatrixEdge[];
  customTypes?: CustomNodeTypeDescriptor[];
  engagementId?: string;
  onNodeClick?: (node: MatrixNode) => void;
}) {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const atParam = searchParams?.get("at") ?? null;
  const resolvedEngagementId = engagementId ?? engagementIdFromPathname(pathname);
  const snapshot = useMatrixSnapshot(resolvedEngagementId, atParam);

  const effectiveNodes = snapshot.kind === "ready" ? snapshot.nodes : nodes;
  const effectiveEdges = snapshot.kind === "ready" ? snapshot.edges : edges;

  const custom = React.useMemo(() => customTypes ?? [], [customTypes]);
  const typeOrder = React.useMemo(
    () => buildTypeOrder(effectiveNodes, custom),
    [effectiveNodes, custom],
  );
  const labelMap = React.useMemo(() => buildLabelMap(custom), [custom]);
  const bgMap = React.useMemo(() => buildBgMap(custom), [custom]);
  const rfNodes = React.useMemo(
    () => buildNodes(effectiveNodes, typeOrder, labelMap, bgMap),
    [effectiveNodes, typeOrder, labelMap, bgMap],
  );
  const rfEdges = React.useMemo(() => buildEdges(effectiveEdges), [effectiveEdges]);
  const nodesById = React.useMemo(() => {
    const m = new Map<string, MatrixNode>();
    for (const n of effectiveNodes) m.set(n.id, n);
    return m;
  }, [effectiveNodes]);

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

  const slider = resolvedEngagementId ? <MatrixTimeSlider /> : null;
  const staleBanner =
    snapshot.kind === "ready" && isSnapshotStale(snapshot.capturedAt, nodes) ? (
      <p
        className="border-border bg-paper-50 text-ink-700 rounded-lg border p-3 text-sm"
        role="status"
        data-testid="matrix-snapshot-stale-banner"
      >
        Snapshot from {formatSnapshotDate(snapshot.capturedAt)}; matrix has changed since.
      </p>
    ) : null;

  if (snapshot.kind === "missing") {
    return (
      <div className="space-y-2">
        {slider}
        <p
          className="border-border bg-paper-50 text-ink-700 rounded-lg border p-3 text-sm"
          role="status"
          data-testid="matrix-snapshot-missing"
        >
          No snapshot for that date.
        </p>
      </div>
    );
  }

  if (snapshot.kind === "error") {
    return (
      <div className="space-y-2">
        {slider}
        <p
          className="border-border bg-paper-50 text-ink-700 rounded-lg border p-3 text-sm"
          role="alert"
        >
          Could not load snapshot: {snapshot.message}
        </p>
      </div>
    );
  }

  if (effectiveNodes.length === 0) {
    return (
      <div className="space-y-2">
        {slider}
        <p className="text-ink-600 text-sm">
          No matrix entities yet — the graph fills in as nodes are added.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {slider}
      {staleBanner}
      <MatrixLegend />
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
    </div>
  );
}
