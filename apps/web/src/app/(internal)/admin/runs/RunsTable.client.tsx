"use client";

import { useMemo, useState } from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

export type RunRow = {
  id: string;
  tenant: string;
  source: string;
  startedAt: string;
  status: string;
  eventCount: number;
  raw: Record<string, string>;
};

function matchesFilter(row: RunRow, q: string): boolean {
  if (!q.trim()) {
    return true;
  }
  const s = q.trim().toLowerCase();
  return (
    row.id.toLowerCase().includes(s) ||
    row.tenant.toLowerCase().includes(s) ||
    row.source.toLowerCase().includes(s) ||
    row.status.toLowerCase().includes(s) ||
    row.startedAt.toLowerCase().includes(s) ||
    String(row.eventCount).includes(s)
  );
}

export function RunsTable({ rows }: { rows: RunRow[] }) {
  const [open, setOpen] = useState(false);
  const [detail, setDetail] = useState<RunRow | null>(null);
  const [query, setQuery] = useState("");

  const visible = useMemo(() => rows.filter((r) => matchesFilter(r, query)), [rows, query]);

  return (
    <>
      <div className="flex max-w-md flex-col gap-2">
        <label className="text-body font-medium text-ink-800" htmlFor="runs-filter">
          Filter runs
        </label>
        <input
          id="runs-filter"
          type="search"
          className="border-ink-200 text-body rounded-md border bg-white px-3 py-2 text-ink-950"
          placeholder="Tenant, source, status, run id…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          autoComplete="off"
        />
      </div>
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Tenant</TableHead>
            <TableHead>Source</TableHead>
            <TableHead>Started</TableHead>
            <TableHead>Status</TableHead>
            <TableHead className="text-right">Events</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visible.map((r) => (
            <TableRow
              key={r.id}
              className="cursor-pointer"
              onClick={() => {
                setDetail(r);
                setOpen(true);
              }}
            >
              <TableCell>{r.tenant}</TableCell>
              <TableCell>{r.source}</TableCell>
              <TableCell>{r.startedAt}</TableCell>
              <TableCell>{r.status}</TableCell>
              <TableCell className="text-right">{r.eventCount}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>

      <Sheet open={open} onOpenChange={setOpen}>
        <SheetContent side="right" className="sm:max-w-lg">
          <SheetHeader>
            <SheetTitle>Run {detail?.id}</SheetTitle>
            <SheetDescription>
              Raw metadata (Story 1-16 shell; Epic 3 wires real runs).
            </SheetDescription>
          </SheetHeader>
          {detail ? (
            <pre className="mt-4 overflow-x-auto rounded-md border p-4 text-xs">
              {JSON.stringify(detail.raw, null, 2)}
            </pre>
          ) : null}
        </SheetContent>
      </Sheet>
    </>
  );
}
