"use client";

import * as React from "react";
import Link from "next/link";

import { CitationChip, ValidationQueueCard } from "@deployai/shared-ui";

import { MORNING_DIGEST_TOP } from "@/lib/epic8/mock-digest";

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
      return;
    }
    const j = (await r.json()) as { items: Row[] };
    setRows(j.items ?? []);
  }, []);

  React.useEffect(() => {
    const t = window.setTimeout(() => {
      void refresh();
    }, 0);
    return () => {
      window.clearTimeout(t);
    };
  }, [refresh]);

  const post = async (body: unknown) => {
    await fetch("/api/bff/solidification-queue", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    await refresh();
  };

  const digest = MORNING_DIGEST_TOP[0];

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">
          Solidification review
        </h1>
        <p className="text-body text-ink-600 mt-1">
          Epic 9.7 — Class B weekly review queue (reuse{" "}
          <code className="font-mono text-xs">ValidationQueueCard</code> per spec).
        </p>
      </div>
      <div className="flex flex-col gap-4">
        {rows.map((row) => (
          <ValidationQueueCard
            key={row.id}
            id={row.id}
            proposedFact={row.proposed_fact}
            confidence={row.confidence}
            state={row.state}
            disabled={row.state === "resolved"}
            supportingEvidence={
              digest ? (
                <CitationChip
                  id={`sq-chip-${row.id}`}
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
              ) : null
            }
            onConfirm={() => post({ op: "promote", id: row.id })}
            onModify={(reason) => post({ op: "demote", id: row.id, reason })}
            onReject={(reason) => post({ op: "demote", id: row.id, reason })}
            onDefer={() => post({ op: "defer", id: row.id })}
          />
        ))}
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
