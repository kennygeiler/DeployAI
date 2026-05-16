"use client";

import * as React from "react";
import Link from "next/link";
import { toast } from "sonner";

import { ValidationQueueCard } from "@deployai/shared-ui";

import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

type Row = {
  id: string;
  proposed_fact: string;
  confidence: string;
  state: "unresolved" | "in-review" | "resolved" | "escalated";
};

export function SolidificationQueueSurface() {
  const [rows, setRows] = React.useState<Row[]>([]);

  const refresh = React.useCallback(async () => {
    const r = await fetch("/api/bff/solidification-queue", { cache: "no-store" });
    if (!r.ok) {
      toast.error("Solidification queue failed to load", {
        description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
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
      const r = await fetch("/api/bff/solidification-queue", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!r.ok) {
        toast.error("Action failed", {
          description: (await readStrategistBffErrorDescription(r)).slice(0, 240),
        });
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
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">
          Solidification review
        </h1>
        <p className="text-body text-ink-600 mt-1">
          Epic 9.7 — Class B weekly review: promote, demote (reason required), or defer. Promoted /
          demoted items leave this queue; deferred items stay for the next cycle.
        </p>
      </div>
      <div className="flex flex-col gap-4">
        {rows.map((row) => {
          return (
            <ValidationQueueCard
              key={row.id}
              id={row.id}
              proposedFact={row.proposed_fact}
              confidence={row.confidence}
              state={row.state}
              disabled={row.state === "resolved" || row.state === "escalated"}
              hideReject
              actionLabels={{ confirm: "Promote", modify: "Demote", defer: "Defer" }}
              statusHints={{
                inReview: "Deferred — on deck for the next Class B review.",
                resolved: "Promoted — marked solidified in this mock store.",
                escalated: "Demoted — returned to candidate tier for rework.",
              }}
              supportingEvidence={
                <span className="text-ink-600 text-xs">
                  Citation preview comes from pilot digest when wired (no local fixtures).
                </span>
              }
              onConfirm={() => post({ op: "promote", id: row.id }, "Promoted (solidified)")}
              onModify={(reason) =>
                post({ op: "demote", id: row.id, reason }, "Demoted to candidate")
              }
              onReject={() => {}}
              onDefer={() => post({ op: "defer", id: row.id }, "Deferred to next review")}
            />
          );
        })}
      </div>
      <Link
        href="/evening"
        className="text-evidence-800 text-sm font-medium underline-offset-2 hover:underline"
      >
        Back to Evening synthesis
      </Link>
    </div>
  );
}
