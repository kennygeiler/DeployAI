"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";

import { CitationChip, ValidationQueueCard } from "@deployai/shared-ui";

import { MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";

type Row = {
  id: string;
  proposed_fact: string;
  confidence: string;
  state: "unresolved" | "in-review" | "resolved" | "escalated";
};

export function ValidationQueueSurface() {
  const [rows, setRows] = React.useState<Row[]>([]);

  const refresh = React.useCallback(async () => {
    const r = await fetch("/api/bff/validation-queue", { cache: "no-store" });
    if (!r.ok) {
      toast.error("Validation queue failed to load", {
        description: (await r.text()).slice(0, 200),
      });
      return;
    }
    const j = (await r.json()) as { items: Row[] };
    setRows(j.items ?? []);
  }, []);

  React.useEffect(() => {
    const t = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(t);
  }, [refresh]);

  const post = React.useCallback(
    async (body: unknown, okMessage: string) => {
      const r = await fetch("/api/bff/validation-queue", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        toast.error("Action failed", { description: (await r.text()).slice(0, 200) });
        return;
      }
      toast.success(okMessage);
      await refresh();
    },
    [refresh],
  );

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Validation queue</h1>
        <p className="text-body text-ink-600 mt-1">
          Epic 9.6 — confirm / modify / reject with reasons (BFF mock; Oracle re-rank wiring
          deferred). Resolved rows drop from this surface.
        </p>
      </div>
      <div className="flex flex-col gap-4">
        {rows.map((row, idx) => {
          const digest = MORNING_DIGEST_TOP[idx % MORNING_DIGEST_TOP.length];
          return (
            <ValidationQueueCard
              key={row.id}
              id={row.id}
              proposedFact={row.proposed_fact}
              confidence={row.confidence}
              state={row.state}
              disabled={row.state === "resolved" || row.state === "escalated"}
              supportingEvidence={
                digest ? (
                  <CitationChip
                    id={`vq-chip-${row.id}`}
                    label={digest.preview.citationId.slice(0, 8)}
                    expanded={false}
                    onToggleExpand={() => {}}
                    variant="compact"
                    preview={digest.preview}
                    onViewEvidence={() => {}}
                    onOverride={() => {}}
                    onCopyLink={() => {}}
                    onCiteInOverride={() => {}}
                  />
                ) : (
                  <span className="text-ink-600 text-xs">No citation fixture</span>
                )
              }
              onConfirm={() =>
                post({ op: "confirm", id: row.id }, "Confirmed — promoted toward canonical")
              }
              onModify={(reason) =>
                post({ op: "modify", id: row.id, reason }, "Modification recorded")
              }
              onReject={(reason) =>
                post({ op: "reject", id: row.id, reason }, "Rejection recorded for re-ranking")
              }
              onDefer={() => post({ op: "defer", id: row.id }, "Deferred to next review")}
            />
          );
        })}
      </div>
      <Link
        href="/digest"
        className="text-evidence-800 text-sm font-medium underline-offset-2 hover:underline"
      >
        Back to Morning digest
      </Link>
    </div>
  );
}
