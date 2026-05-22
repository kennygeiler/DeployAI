"use client";

import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import type { EngagementLogEntry } from "@/lib/bff/engagement-log-types";

const KINDS = ["meeting", "decision", "risk", "next_action"] as const;

/**
 * Phase 3 — manual capture. Logs a meeting / decision / risk / next-action
 * note against the selected engagement and shows the most recent entries.
 */
export function EngagementCaptureForm({ engagementId }: { engagementId: string }) {
  const [kind, setKind] = React.useState<string>("meeting");
  const [body, setBody] = React.useState("");
  const [entries, setEntries] = React.useState<EngagementLogEntry[]>([]);
  const [submitting, setSubmitting] = React.useState(false);

  const refresh = React.useCallback(async () => {
    const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}/log`, {
      cache: "no-store",
    });
    if (r.ok) {
      const j = (await r.json()) as { entries?: EngagementLogEntry[] };
      setEntries(j.entries ?? []);
    }
  }, [engagementId]);

  React.useEffect(() => {
    const t = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(t);
  }, [refresh]);

  const submit = React.useCallback(async () => {
    const text = body.trim();
    if (!text) {
      return;
    }
    setSubmitting(true);
    try {
      const r = await fetch(`/api/bff/engagements/${encodeURIComponent(engagementId)}/log`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ entry_kind: kind, body: text }),
      });
      if (!r.ok) {
        toast.error("Could not log the entry");
        return;
      }
      toast.success("Entry logged");
      setBody("");
      await refresh();
    } finally {
      setSubmitting(false);
    }
  }, [body, engagementId, kind, refresh]);

  return (
    <div className="border-border space-y-2 rounded-lg border p-3">
      <h2 className="text-ink-800 text-sm font-semibold">Log an entry</h2>
      <div className="flex flex-wrap items-start gap-2">
        <label className="sr-only" htmlFor="log-entry-kind">
          Entry kind
        </label>
        <select
          id="log-entry-kind"
          className="border-border rounded-md border px-2 py-1 text-sm"
          value={kind}
          onChange={(e) => setKind(e.target.value)}
        >
          {KINDS.map((k) => (
            <option key={k} value={k}>
              {k.replace("_", " ")}
            </option>
          ))}
        </select>
        <label className="sr-only" htmlFor="log-entry-body">
          Entry
        </label>
        <textarea
          id="log-entry-body"
          className="border-border min-h-16 flex-1 rounded-md border px-2 py-1 text-sm"
          placeholder="What happened, was decided, or is at risk…"
          value={body}
          onChange={(e) => setBody(e.target.value)}
        />
        <Button type="button" size="sm" disabled={submitting || !body.trim()} onClick={() => void submit()}>
          Log
        </Button>
      </div>
      {entries.length > 0 ? (
        <ul className="text-ink-700 space-y-1 text-xs">
          {entries.slice(0, 5).map((e) => (
            <li key={e.id}>
              <span className="font-mono">{e.entry_kind}</span> — {e.body}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
