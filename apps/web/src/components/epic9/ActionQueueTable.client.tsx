"use client";

import * as React from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import type { ActionQueueItem } from "@/lib/bff/strategist-queues-store";

export function ActionQueueTable() {
  const [items, setItems] = React.useState<ActionQueueItem[]>([]);
  const [err, setErr] = React.useState<string | null>(null);

  const refresh = React.useCallback(async () => {
    const r = await fetch("/api/bff/action-queue", { cache: "no-store" });
    if (!r.ok) {
      setErr(await r.text());
      return;
    }
    setErr(null);
    const j = (await r.json()) as { items: ActionQueueItem[] };
    setItems(j.items ?? []);
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
    const r = await fetch("/api/bff/action-queue", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!r.ok) {
      setErr(await r.text());
      return;
    }
    await refresh();
  };

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-display text-ink-950 font-semibold tracking-tight">Action queue</h1>
          <p className="text-body text-ink-600 mt-1 max-w-2xl">
            Epic 9.5 — lifecycle against the in-process BFF store (carryovers from Epic 9.4 appear
            here with <code className="font-mono text-xs">source: in_meeting_alert</code>).
          </p>
        </div>
        <Button type="button" variant="outline" size="sm" onClick={() => void refresh()}>
          Refresh
        </Button>
      </div>
      {err ? <p className="text-destructive text-sm">{err}</p> : null}
      <div className="border-border overflow-x-auto rounded-lg border">
        <table className="w-full min-w-[42rem] text-left text-sm">
          <thead className="bg-paper-200/80 text-ink-700">
            <tr>
              <th className="px-3 py-2 font-medium">Priority</th>
              <th className="px-3 py-2 font-medium">Phase</th>
              <th className="px-3 py-2 font-medium">Description</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Claimed by</th>
              <th className="px-3 py-2 font-medium">Updated</th>
              <th className="px-3 py-2 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td className="text-ink-600 px-3 py-6" colSpan={7}>
                  No rows yet — resolve an in-meeting session with unattended primaries (Epic 9.4)
                  or insert fixtures via the BFF in tests.
                </td>
              </tr>
            ) : (
              items.map((row) => (
                <tr key={row.id} className="border-t border-border">
                  <td className="px-3 py-2">{row.priority}</td>
                  <td className="px-3 py-2">{row.phase}</td>
                  <td className="px-3 py-2">{row.description}</td>
                  <td className="px-3 py-2 font-mono text-xs">{row.status}</td>
                  <td className="px-3 py-2">{row.claimed_by ?? "—"}</td>
                  <td className="px-3 py-2 font-mono text-xs">{row.updated_at}</td>
                  <td className="px-3 py-2">
                    <div className="flex flex-wrap gap-1">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => void post({ op: "claim", id: row.id })}
                      >
                        Claim
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => void post({ op: "progress", id: row.id })}
                      >
                        In progress
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className="h-7 px-2 text-xs"
                        onClick={() => void post({ op: "resolve", id: row.id, state: "resolved" })}
                      >
                        Resolve
                      </Button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
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
