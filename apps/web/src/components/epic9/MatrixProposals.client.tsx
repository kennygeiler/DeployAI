"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { MatrixNode, MatrixProposal } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

/**
 * Phase 6 (increment 6.2a) — review pending matrix proposals. The Cartographer
 * extraction agent (6.2b) writes proposals citing the canonical event they
 * were derived from; accept commits the proposed node/edge into the matrix
 * with that event as its evidence; reject closes the proposal out.
 */
export function MatrixProposals({
  engagementId,
  proposals,
  nodes,
  onChanged,
}: {
  engagementId: string;
  proposals: MatrixProposal[];
  nodes: MatrixNode[];
  onChanged: () => void | Promise<void>;
}) {
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const decide = React.useCallback(
    async (proposalId: string, decision: "accept" | "reject") => {
      setBusyId(proposalId);
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/proposals/` +
            `${encodeURIComponent(proposalId)}/${decision}`,
          { method: "POST" },
        );
        if (!r.ok) {
          toast.error(
            decision === "accept" ? "Could not accept proposal" : "Could not reject proposal",
            {
              description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
            },
          );
          return;
        }
        toast.success(decision === "accept" ? "Proposal accepted" : "Proposal rejected");
        await onChanged();
      } finally {
        setBusyId(null);
      }
    },
    [engagementId, onChanged],
  );

  if (proposals.length === 0) {
    return (
      <p className="text-ink-600 text-sm">
        No proposals pending — the extraction agent (Phase 6.2b) will surface candidate matrix
        entities here as interactions are imported.
      </p>
    );
  }

  const titleById = new Map(nodes.map((n) => [n.id, n.title] as const));

  return (
    <ul className="border-border divide-border divide-y rounded-lg border text-sm">
      {proposals.map((p) => (
        <li key={p.id} className="space-y-1 px-3 py-2">
          <div className="flex items-center justify-between gap-3">
            <span className="text-ink-600 font-mono text-xs uppercase">{p.proposal_kind}</span>
            <div className="flex gap-1">
              <Button
                type="button"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={busyId === p.id}
                onClick={() => void decide(p.id, "accept")}
              >
                Accept
              </Button>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="h-7 px-2 text-xs"
                disabled={busyId === p.id}
                onClick={() => void decide(p.id, "reject")}
              >
                Reject
              </Button>
            </div>
          </div>
          <p className="text-ink-800">{summarize(p, titleById)}</p>
          {p.rationale ? <p className="text-ink-500 text-xs">{p.rationale}</p> : null}
        </li>
      ))}
    </ul>
  );
}

function summarize(p: MatrixProposal, titleById: Map<string, string>): string {
  const payload = p.payload ?? {};
  if (p.proposal_kind === "node") {
    const nodeType = typeof payload.node_type === "string" ? payload.node_type : "node";
    const title = typeof payload.title === "string" ? payload.title : "(no title)";
    return `${nodeType}: ${title}`;
  }
  if (p.proposal_kind === "edge") {
    const edgeType = typeof payload.edge_type === "string" ? payload.edge_type : "edge";
    const fromId = typeof payload.from_node_id === "string" ? payload.from_node_id : "";
    const toId = typeof payload.to_node_id === "string" ? payload.to_node_id : "";
    const fromLabel = titleById.get(fromId) ?? fromId.slice(0, 8) ?? "?";
    const toLabel = titleById.get(toId) ?? toId.slice(0, 8) ?? "?";
    return `${fromLabel} —${edgeType.replace("_", " ")}→ ${toLabel}`;
  }
  return p.proposal_kind;
}
