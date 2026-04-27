"use client";

import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import Link from "next/link";
import * as React from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { ActionQueueItem } from "@/lib/bff/strategist-queues-store";

const columnHelper = createColumnHelper<ActionQueueItem>();

type ResolveState = "resolved" | "deferred" | "rejected_with_reason";

export function ActionQueueTable() {
  const [items, setItems] = React.useState<ActionQueueItem[]>([]);
  const [err, setErr] = React.useState<string | null>(null);
  const [resolveOpen, setResolveOpen] = React.useState(false);
  const [resolveRow, setResolveRow] = React.useState<ActionQueueItem | null>(null);
  const [resolveState, setResolveState] = React.useState<ResolveState>("resolved");
  const [resolveReason, setResolveReason] = React.useState("");
  const [resolveEvidence, setResolveEvidence] = React.useState("");

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
    const t = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(t);
  }, [refresh]);

  const postClaim = React.useCallback(
    async (id: string) => {
      const r = await fetch(`/api/bff/action-queue/${encodeURIComponent(id)}/claim`, {
        method: "POST",
      });
      if (!r.ok) {
        toast.error("Claim failed", { description: (await r.text()).slice(0, 240) });
        return;
      }
      toast.success("Claimed");
      await refresh();
    },
    [refresh],
  );

  const postProgress = React.useCallback(
    async (id: string) => {
      const r = await fetch(`/api/bff/action-queue/${encodeURIComponent(id)}/progress`, {
        method: "POST",
      });
      if (!r.ok) {
        toast.error("Progress update failed", {
          description: (await r.text()).slice(0, 240),
        });
        return;
      }
      toast.success("Marked in progress");
      await refresh();
    },
    [refresh],
  );

  const openResolve = (row: ActionQueueItem) => {
    setResolveRow(row);
    setResolveState("resolved");
    setResolveReason("");
    setResolveEvidence("");
    setResolveOpen(true);
  };

  const submitResolve = React.useCallback(async () => {
    if (!resolveRow) {
      return;
    }
    if (resolveState === "rejected_with_reason" && !resolveReason.trim()) {
      toast.error("Reason required for rejection");
      return;
    }
    const evidenceIds = resolveEvidence
      .split(/[\s,]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const r = await fetch(`/api/bff/action-queue/${encodeURIComponent(resolveRow.id)}/resolve`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({
        state: resolveState,
        reason: resolveReason.trim() || undefined,
        evidence_event_ids: evidenceIds.length > 0 ? evidenceIds : undefined,
      }),
    });
    if (!r.ok) {
      toast.error("Resolve failed", { description: (await r.text()).slice(0, 240) });
      return;
    }
    toast.success("Resolution recorded");
    setResolveOpen(false);
    await refresh();
  }, [resolveEvidence, resolveReason, resolveRow, resolveState, refresh]);

  const columns = [
    columnHelper.accessor("priority", { header: "Priority" }),
    columnHelper.accessor("phase", { header: "Phase" }),
    columnHelper.accessor("description", { header: "Description" }),
    columnHelper.accessor("status", {
      header: "Status",
      cell: (info) => <span className="font-mono text-xs">{info.getValue()}</span>,
    }),
    columnHelper.accessor("claimed_by", {
      header: "Claimed by",
      cell: (info) => info.getValue() ?? "—",
    }),
    columnHelper.accessor("updated_at", {
      header: "Updated",
      cell: (info) => <span className="font-mono text-xs">{info.getValue()}</span>,
    }),
    columnHelper.display({
      id: "actions",
      header: "Actions",
      cell: (ctx) => {
        const row = ctx.row.original;
        const terminal =
          row.status === "resolved" ||
          row.status === "deferred" ||
          row.status === "rejected_with_reason";
        if (terminal) {
          return <span className="text-ink-500 text-xs">—</span>;
        }
        return (
          <div className="flex flex-wrap gap-1">
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => void postClaim(row.id)}
            >
              Claim
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => void postProgress(row.id)}
            >
              In progress
            </Button>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-7 px-2 text-xs"
              onClick={() => openResolve(row)}
            >
              Resolve…
            </Button>
          </div>
        );
      },
    }),
  ];

  /* TanStack Table's useReactTable is intentionally excluded from React Compiler memoization. */
  // eslint-disable-next-line react-hooks/incompatible-library -- @tanstack/react-table stable pattern
  const table = useReactTable({
    data: items,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="max-w-5xl space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-display text-ink-950 font-semibold tracking-tight">Action queue</h1>
          <p className="text-body text-ink-600 mt-1 max-w-2xl">
            Epic 9.5 — TanStack Table + REST lifecycle{" "}
            <code className="font-mono text-xs">
              POST /api/bff/action-queue/:id/claim|progress|resolve
            </code>
            . Carryovers from Epic 9.4 use{" "}
            <code className="font-mono text-xs">source: in_meeting_alert</code>.
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
            {table.getHeaderGroups().map((hg) => (
              <tr key={hg.id}>
                {hg.headers.map((h) => (
                  <th key={h.id} className="px-3 py-2 font-medium">
                    {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.length === 0 ? (
              <tr>
                <td className="text-ink-600 px-3 py-6" colSpan={columns.length}>
                  No rows yet — resolve an in-meeting session with unattended primaries (Epic 9.4)
                  or insert fixtures via the BFF in tests.
                </td>
              </tr>
            ) : (
              table.getRowModel().rows.map((row) => (
                <tr key={row.id} className="border-t border-border">
                  {row.getVisibleCells().map((cell) => (
                    <td key={cell.id} className="px-3 py-2">
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  ))}
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

      <Dialog open={resolveOpen} onOpenChange={setResolveOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Resolve action item</DialogTitle>
            <DialogDescription>
              Choose resolution state. Rejection requires a reason (Oracle re-rank per FR53).
              Optional evidence event IDs (comma- or space-separated).
            </DialogDescription>
          </DialogHeader>
          <div className="grid gap-3 py-2">
            <div className="grid gap-1">
              <Label htmlFor="resolve-state">State</Label>
              <select
                id="resolve-state"
                className="border-input bg-background h-9 rounded-md border px-2 text-sm"
                value={resolveState}
                onChange={(e) => setResolveState(e.target.value as ResolveState)}
              >
                <option value="resolved">Resolved</option>
                <option value="deferred">Deferred</option>
                <option value="rejected_with_reason">Rejected (reason required)</option>
              </select>
            </div>
            <div className="grid gap-1">
              <Label htmlFor="resolve-reason">Reason (required if rejected)</Label>
              <Input
                id="resolve-reason"
                value={resolveReason}
                onChange={(e) => setResolveReason(e.target.value)}
                placeholder="Why deferred or rejected…"
              />
            </div>
            <div className="grid gap-1">
              <Label htmlFor="resolve-evidence">Evidence event IDs (optional)</Label>
              <Input
                id="resolve-evidence"
                value={resolveEvidence}
                onChange={(e) => setResolveEvidence(e.target.value)}
                placeholder="evt_1, evt_2"
              />
            </div>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setResolveOpen(false)}>
              Cancel
            </Button>
            <Button type="button" onClick={() => void submitResolve()}>
              Submit
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
