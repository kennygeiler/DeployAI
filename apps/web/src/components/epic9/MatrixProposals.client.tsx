"use client";

import * as React from "react";
import { toast } from "sonner";

import { TimestampLabel } from "@/components/common/TimestampLabel.client";
import { Button } from "@/components/ui/button";
import type { MatrixNode, MatrixProposal } from "@/lib/bff/matrix-types";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

/**
 * Phase 6 (increment 6.2a) — review pending matrix proposals. The Cartographer
 * extraction agent (6.2b) writes proposals citing the canonical event they
 * were derived from; accept commits the proposed node/edge into the matrix
 * with that event as its evidence; reject closes the proposal out.
 *
 * Polish.1 — proposals are grouped by (kind, type, summary) so duplicate
 * extractions (one stakeholder mentioned in N events) collapse into one
 * card. Filter by kind / type + expand a group to see each underlying
 * proposal's rationale. Group-level Accept = accept the first row + reject
 * the rest as dupes; group-level Reject = reject all in the group.
 */

const NODE_TYPE_OPTIONS = [
  "stakeholder",
  "organization",
  "system",
  "decision",
  "risk",
  "commitment",
  "opportunity",
] as const;

const EDGE_TYPE_OPTIONS = [
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

type KindFilter = "all" | "node" | "edge";

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
  const [busyIds, setBusyIds] = React.useState<Set<string>>(new Set());
  const [kind, setKind] = React.useState<KindFilter>("all");
  const [typeFilter, setTypeFilter] = React.useState<string>("all");
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set());

  const titleById = React.useMemo(
    () => new Map(nodes.map((n) => [n.id, n.title] as const)),
    [nodes],
  );

  const markBusy = React.useCallback((ids: string[], busy: boolean) => {
    setBusyIds((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (busy) {
          next.add(id);
        } else {
          next.delete(id);
        }
      }
      return next;
    });
  }, []);

  const decideOne = React.useCallback(
    async (proposalId: string, decision: "accept" | "reject"): Promise<boolean> => {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/proposals/` +
          `${encodeURIComponent(proposalId)}/${decision}`,
        { method: "POST" },
      );
      if (!r.ok) {
        toast.error(
          decision === "accept" ? "Could not accept proposal" : "Could not reject proposal",
          { description: (await readStrategistBffErrorDescription(r)).slice(0, 240) },
        );
        return false;
      }
      return true;
    },
    [engagementId],
  );

  const handleSingle = React.useCallback(
    async (proposalId: string, decision: "accept" | "reject") => {
      markBusy([proposalId], true);
      try {
        const ok = await decideOne(proposalId, decision);
        if (ok) {
          toast.success(decision === "accept" ? "Proposal accepted" : "Proposal rejected");
          await onChanged();
        }
      } finally {
        markBusy([proposalId], false);
      }
    },
    [decideOne, markBusy, onChanged],
  );

  const handleGroup = React.useCallback(
    async (groupProposals: MatrixProposal[], decision: "accept" | "reject") => {
      const ids = groupProposals.map((p) => p.id);
      markBusy(ids, true);
      try {
        if (decision === "reject") {
          // Reject every proposal in the group; preserves all rationales as
          // history, removes the group from the pending queue.
          let okCount = 0;
          for (const p of groupProposals) {
            if (await decideOne(p.id, "reject")) {
              okCount += 1;
            }
          }
          if (okCount > 0) {
            toast.success(`Rejected ${okCount} duplicate(s)`);
            await onChanged();
          }
        } else {
          // Accept ONE (the first) — the rest are dupes and get rejected so
          // the matrix doesn't end up with N identical nodes. The single
          // accepted row's `evidence_event_ids` will be `[source_event_id]`
          // of just the first event; manually adding the others is a later
          // polish (would need a merge-accept endpoint).
          const [head, ...tail] = groupProposals;
          if (!head) {
            return;
          }
          const okHead = await decideOne(head.id, "accept");
          let rejectedDupes = 0;
          if (okHead) {
            for (const p of tail) {
              if (await decideOne(p.id, "reject")) {
                rejectedDupes += 1;
              }
            }
            const msg =
              tail.length === 0
                ? "Proposal accepted"
                : `Accepted; rejected ${rejectedDupes} duplicate(s)`;
            toast.success(msg);
            await onChanged();
          }
        }
      } finally {
        markBusy(ids, false);
      }
    },
    [decideOne, markBusy, onChanged],
  );

  const filtered = React.useMemo(() => {
    return proposals.filter((p) => {
      if (kind !== "all" && p.proposal_kind !== kind) {
        return false;
      }
      if (typeFilter !== "all") {
        const payload = (p.payload ?? {}) as Record<string, unknown>;
        const t =
          p.proposal_kind === "node" && typeof payload.node_type === "string"
            ? payload.node_type
            : p.proposal_kind === "edge" && typeof payload.edge_type === "string"
              ? payload.edge_type
              : null;
        if (t !== typeFilter) {
          return false;
        }
      }
      return true;
    });
  }, [proposals, kind, typeFilter]);

  const groups = React.useMemo(() => {
    const map = new Map<string, { key: string; label: string; items: MatrixProposal[] }>();
    for (const p of filtered) {
      const label = summarize(p, titleById);
      const key = `${p.proposal_kind}|${label}`;
      const existing = map.get(key);
      if (existing) {
        existing.items.push(p);
      } else {
        map.set(key, { key, label, items: [p] });
      }
    }
    return Array.from(map.values()).sort((a, b) => {
      if (a.items.length !== b.items.length) {
        return b.items.length - a.items.length;
      }
      return a.label.localeCompare(b.label);
    });
  }, [filtered, titleById]);

  // The available type-filter options depend on the kind filter.
  const typeOptions: readonly string[] =
    kind === "node"
      ? NODE_TYPE_OPTIONS
      : kind === "edge"
        ? EDGE_TYPE_OPTIONS
        : ([...NODE_TYPE_OPTIONS, ...EDGE_TYPE_OPTIONS] as const);

  if (proposals.length === 0) {
    return (
      <p className="text-ink-600 text-sm">
        No proposals pending — the matrix-extraction agent will surface candidate matrix entities
        here as interactions are imported.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3" role="group" aria-label="Filter proposals">
        <div className="grid gap-1">
          <label className="text-ink-600 text-xs" htmlFor="proposals-filter-kind">
            Kind
          </label>
          <select
            id="proposals-filter-kind"
            className="border-border rounded-md border px-2 py-1 text-sm"
            value={kind}
            onChange={(e) => {
              setKind(e.target.value as KindFilter);
              setTypeFilter("all");
            }}
          >
            <option value="all">All</option>
            <option value="node">Nodes</option>
            <option value="edge">Edges</option>
          </select>
        </div>
        <div className="grid gap-1">
          <label className="text-ink-600 text-xs" htmlFor="proposals-filter-type">
            Type
          </label>
          <select
            id="proposals-filter-type"
            className="border-border rounded-md border px-2 py-1 text-sm"
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
          >
            <option value="all">All</option>
            {typeOptions.map((t) => (
              <option key={t} value={t}>
                {t.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>
        <p className="text-ink-600 text-xs">
          {filtered.length} of {proposals.length} proposal(s) — {groups.length} unique
        </p>
      </div>

      {groups.length === 0 ? (
        <p className="text-ink-600 text-sm">No proposals match the current filter.</p>
      ) : (
        <ul
          className="border-border divide-border divide-y rounded-lg border text-sm"
          aria-label="Pending proposal groups"
        >
          {groups.map((g) => {
            const isOpen = expanded.has(g.key);
            const groupBusy = g.items.some((p) => busyIds.has(p.id));
            const kindLabel = g.items[0]?.proposal_kind ?? "—";
            return (
              <li key={g.key} className="space-y-1 px-3 py-2">
                <div className="flex items-center justify-between gap-3">
                  <Button
                    type="button"
                    variant="ghost"
                    className="text-ink-800 hover:bg-ink-50 flex h-auto flex-1 items-center justify-start gap-2 px-1 py-0 text-left font-medium"
                    onClick={() =>
                      setExpanded((prev) => {
                        const next = new Set(prev);
                        if (next.has(g.key)) {
                          next.delete(g.key);
                        } else {
                          next.add(g.key);
                        }
                        return next;
                      })
                    }
                    aria-expanded={isOpen}
                  >
                    <span className="text-ink-500 font-mono text-xs">{isOpen ? "▾" : "▸"}</span>
                    <span className="text-ink-600 font-mono text-xs uppercase">{kindLabel}</span>
                    <span>{g.label}</span>
                    {g.items.length > 1 ? (
                      <span className="bg-ink-100 text-ink-700 rounded px-1.5 py-0.5 font-mono text-[10px]">
                        ×{g.items.length}
                      </span>
                    ) : null}
                  </Button>
                  <div className="flex gap-1">
                    <Button
                      type="button"
                      size="sm"
                      className="h-7 px-2 text-xs"
                      disabled={groupBusy}
                      onClick={() => void handleGroup(g.items, "accept")}
                    >
                      {g.items.length > 1 ? "Accept (dedup)" : "Accept"}
                    </Button>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-7 px-2 text-xs"
                      disabled={groupBusy}
                      onClick={() => void handleGroup(g.items, "reject")}
                    >
                      Reject{g.items.length > 1 ? " all" : ""}
                    </Button>
                  </div>
                </div>
                {isOpen ? (
                  <ul
                    className="border-border bg-ink-50/50 mt-2 ml-5 space-y-1 rounded border p-2 text-xs"
                    aria-label={`Underlying proposals for ${g.label}`}
                  >
                    {g.items.map((p) => (
                      <li
                        key={p.id}
                        className="border-border flex items-start justify-between gap-2 border-b pb-1 last:border-none last:pb-0"
                      >
                        <div className="flex-1 space-y-0.5">
                          {p.rationale ? (
                            <p className="text-ink-700">{p.rationale}</p>
                          ) : (
                            <p className="text-ink-500 italic">(no rationale)</p>
                          )}
                          <div className="flex flex-wrap items-center gap-2">
                            <TimestampLabel value={p.created_at} prefix="proposed" />
                            {p.decided_at ? (
                              <TimestampLabel value={p.decided_at} prefix="decided" />
                            ) : null}
                            <span className="text-ink-400 font-mono text-[10px]">
                              src: {p.source_event_id.slice(0, 8)}…
                            </span>
                          </div>
                        </div>
                        <div className="flex gap-1">
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="h-6 px-1.5 text-[10px]"
                            disabled={busyIds.has(p.id)}
                            onClick={() => void handleSingle(p.id, "accept")}
                          >
                            Accept
                          </Button>
                          <Button
                            type="button"
                            size="sm"
                            variant="ghost"
                            className="h-6 px-1.5 text-[10px]"
                            disabled={busyIds.has(p.id)}
                            onClick={() => void handleSingle(p.id, "reject")}
                          >
                            Reject
                          </Button>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

function summarize(p: MatrixProposal, titleById: Map<string, string>): string {
  const payload = (p.payload ?? {}) as Record<string, unknown>;
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
