"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { MatrixNode } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

const NODE_TYPES = [
  "stakeholder",
  "organization",
  "system",
  "decision",
  "risk",
  "commitment",
  "opportunity",
] as const;

const NODE_TYPE_LABEL: Record<string, string> = {
  stakeholder: "Stakeholder",
  organization: "Organization",
  system: "System",
  decision: "Decision",
  risk: "Risk",
  commitment: "Commitment",
  opportunity: "Opportunity",
};

const EDGE_TYPES = [
  "belongs_to",
  "owns",
  "sponsors",
  "blocks",
  "affects",
  "threatens",
  "owed_by",
  "owed_to",
  "depends_on",
  "enables",
] as const;

const SELECT_CLASS = "border-border rounded-md border px-2 py-1 text-sm";

/**
 * Phase 5 — structured capture. Adds typed entities (nodes) and
 * relationships (edges) to an engagement's deployment matrix. The
 * manual-entry harness that Phase 6 unifies with the automated ones.
 */
export function MatrixCapture({
  engagementId,
  nodes,
  onChanged,
}: {
  engagementId: string;
  nodes: MatrixNode[];
  onChanged: () => void | Promise<void>;
}) {
  const [nodeType, setNodeType] = React.useState<string>("system");
  const [title, setTitle] = React.useState("");
  const [edgeFrom, setEdgeFrom] = React.useState("");
  const [edgeType, setEdgeType] = React.useState<string>("depends_on");
  const [edgeTo, setEdgeTo] = React.useState("");
  const [busy, setBusy] = React.useState(false);

  const addNode = React.useCallback(async () => {
    const text = title.trim();
    if (!text) {
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/matrix/nodes`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ node_type: nodeType, title: text }),
        },
      );
      if (!r.ok) {
        toast.error("Could not add entity", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
        return;
      }
      toast.success("Entity added");
      setTitle("");
      await onChanged();
    } finally {
      setBusy(false);
    }
  }, [engagementId, nodeType, title, onChanged]);

  const addEdge = React.useCallback(async () => {
    if (!edgeFrom || !edgeTo || edgeFrom === edgeTo) {
      return;
    }
    setBusy(true);
    try {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/matrix/edges`,
        {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({
            edge_type: edgeType,
            from_node_id: edgeFrom,
            to_node_id: edgeTo,
          }),
        },
      );
      if (!r.ok) {
        toast.error("Could not add link", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
        return;
      }
      toast.success("Link added");
      setEdgeFrom("");
      setEdgeTo("");
      await onChanged();
    } finally {
      setBusy(false);
    }
  }, [engagementId, edgeType, edgeFrom, edgeTo, onChanged]);

  return (
    <div className="border-border space-y-3 rounded-lg border p-3">
      <h3 className="text-ink-800 text-xs font-semibold">Add to the matrix</h3>

      <div className="flex flex-wrap items-end gap-2">
        <div className="grid gap-1">
          <label className="text-ink-600 text-xs" htmlFor="matrix-node-type">
            Entity type
          </label>
          <select
            id="matrix-node-type"
            className={SELECT_CLASS}
            value={nodeType}
            onChange={(e) => setNodeType(e.target.value)}
          >
            {NODE_TYPES.map((t) => (
              <option key={t} value={t}>
                {NODE_TYPE_LABEL[t]}
              </option>
            ))}
          </select>
        </div>
        <div className="grid gap-1">
          <label className="text-ink-600 text-xs" htmlFor="matrix-node-title">
            Title
          </label>
          <input
            id="matrix-node-title"
            className={SELECT_CLASS}
            placeholder="e.g. LiDAR ingest"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <Button
          type="button"
          size="sm"
          disabled={busy || !title.trim()}
          onClick={() => void addNode()}
        >
          Add entity
        </Button>
      </div>

      {nodes.length >= 2 ? (
        <div className="flex flex-wrap items-end gap-2">
          <div className="grid gap-1">
            <label className="text-ink-600 text-xs" htmlFor="matrix-edge-from">
              From
            </label>
            <select
              id="matrix-edge-from"
              className={SELECT_CLASS}
              value={edgeFrom}
              onChange={(e) => setEdgeFrom(e.target.value)}
            >
              <option value="">Choose…</option>
              {nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.title}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-1">
            <label className="text-ink-600 text-xs" htmlFor="matrix-edge-type">
              Relationship
            </label>
            <select
              id="matrix-edge-type"
              className={SELECT_CLASS}
              value={edgeType}
              onChange={(e) => setEdgeType(e.target.value)}
            >
              {EDGE_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.replace("_", " ")}
                </option>
              ))}
            </select>
          </div>
          <div className="grid gap-1">
            <label className="text-ink-600 text-xs" htmlFor="matrix-edge-to">
              To
            </label>
            <select
              id="matrix-edge-to"
              className={SELECT_CLASS}
              value={edgeTo}
              onChange={(e) => setEdgeTo(e.target.value)}
            >
              <option value="">Choose…</option>
              {nodes.map((n) => (
                <option key={n.id} value={n.id}>
                  {n.title}
                </option>
              ))}
            </select>
          </div>
          <Button
            type="button"
            size="sm"
            disabled={busy || !edgeFrom || !edgeTo || edgeFrom === edgeTo}
            onClick={() => void addEdge()}
          >
            Add link
          </Button>
        </div>
      ) : null}
    </div>
  );
}
