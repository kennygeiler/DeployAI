"use client";

import * as React from "react";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  getSortedRowModel,
  useReactTable,
  type SortingState,
} from "@tanstack/react-table";

import { EvidencePanel } from "@deployai/shared-ui";
import type { ActionQueueRow } from "@/lib/epic8/mock-digest";
import { PHASE_TRACKING_ROWS } from "@/lib/epic8/mock-digest";
import { useStrategistSurface } from "@/lib/epic8/strategist-surface-context";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { cn } from "@/lib/utils";

const columnHelper = createColumnHelper<ActionQueueRow>();

const phaseOptions = ["All", "P5 Pilot", "P4 Design"] as const;
const statusOptions = ["All", "open", "in_progress", "blocked"] as const;

const assigneeOptions = [
  "All",
  ...Array.from(new Set(PHASE_TRACKING_ROWS.map((r) => r.assignee))).sort((a, b) =>
    a.localeCompare(b, "en"),
  ),
] as const;

function statusLabel(s: ActionQueueRow["status"]): string {
  if (s === "in_progress") {
    return "In progress";
  }
  if (s === "blocked") {
    return "Blocked";
  }
  return "Open";
}

function statusSort(a: string, b: string): number {
  const o = (x: string) => (x === "blocked" ? 0 : x === "in_progress" ? 1 : 2);
  return o(a) - o(b);
}

export function PhaseTrackingClient() {
  const { agentDegraded } = useStrategistSurface();
  const [phaseFilter, setPhaseFilter] = React.useState<(typeof phaseOptions)[number]>("All");
  const [statusFilter, setStatusFilter] = React.useState<(typeof statusOptions)[number]>("All");
  const [assigneeFilter, setAssigneeFilter] = React.useState<(typeof assigneeOptions)[number]>("All");
  const [sorting, setSorting] = React.useState<SortingState>([
    { id: "priority", desc: false },
    { id: "due", desc: false },
  ]);
  const [selectedId, setSelectedId] = React.useState(PHASE_TRACKING_ROWS[0]!.id);

  const rows = React.useMemo(() => {
    return PHASE_TRACKING_ROWS.filter((r) => {
      if (phaseFilter !== "All" && r.phase !== phaseFilter) {
        return false;
      }
      if (statusFilter !== "All" && r.status !== statusFilter) {
        return false;
      }
      if (assigneeFilter !== "All" && r.assignee !== assigneeFilter) {
        return false;
      }
      return true;
    });
  }, [phaseFilter, statusFilter, assigneeFilter]);

  React.useEffect(() => {
    if (rows.length === 0) {
      setSelectedId("");
      return;
    }
    if (!selectedId || !rows.some((r) => r.id === selectedId)) {
      setSelectedId(rows[0]!.id);
    }
  }, [rows, selectedId]);

  const columns = React.useMemo(
    () => [
      columnHelper.accessor("title", {
        header: "Title",
        cell: (c) => <span className="font-medium text-ink-900">{c.getValue()}</span>,
      }),
      columnHelper.accessor("phase", { header: "Phase" }),
      columnHelper.accessor("status", {
        header: "Status",
        sortingFn: (ra, rb, id) => statusSort(ra.getValue(id), rb.getValue(id)),
        cell: (c) => {
          const v = c.getValue();
          return (
            <Badge
              variant={
                v === "blocked" ? "destructive" : v === "in_progress" ? "default" : "secondary"
              }
              className="font-normal"
            >
              {statusLabel(v)}
            </Badge>
          );
        },
      }),
      columnHelper.accessor("assignee", { header: "Assignee" }),
      columnHelper.accessor("due", { header: "Due" }),
      columnHelper.accessor("priority", {
        header: "Priority",
        cell: (c) => <span className="tabular-nums">{c.getValue()}</span>,
      }),
    ],
    [],
  );

  // TanStack Table returns unstable function refs; React Compiler intentionally skips this subtree.
  // eslint-disable-next-line react-hooks/incompatible-library -- useReactTable (TanStack) is vetted for this table
  const table = useReactTable({
    data: [...rows],
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getRowId: (r) => r.id,
  });

  const modelRows = table.getRowModel().rows;
  const selectedRow = React.useMemo(() => {
    if (!selectedId) {
      return null;
    }
    return modelRows.find((r) => r.original.id === selectedId)?.original ?? null;
  }, [modelRows, selectedId]);
  const selectedIdx = selectedRow
    ? modelRows.findIndex((r) => r.original.id === selectedRow.id)
    : -1;
  const liveDetail =
    selectedRow && selectedIdx >= 0
      ? `Row ${selectedIdx + 1} of ${modelRows.length} — ${selectedRow.title}`
      : "No row selected.";

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">
          Phase &amp; task tracking
        </h1>
        <p className="text-body text-ink-600 mt-1 max-w-2xl">
          Action queue, blockers, and phase context (FR39). Default sort: priority, then due date.
        </p>
        {agentDegraded ? (
          <p
            className="text-ink-800 mt-2 max-w-2xl rounded-md border border-amber-600/30 bg-amber-50/80 px-3 py-2 text-sm"
            role="status"
          >
            Action-queue suggestions may be stale while agents recover. Canonical evidence still
            reads normally (FR46).
          </p>
        ) : null}
      </div>
      <div className="flex min-h-0 min-w-0 flex-1 flex-col gap-3 lg:flex-row">
        <div className="border-border min-h-[320px] min-w-0 flex-1 overflow-hidden rounded-lg border lg:min-h-[480px]">
          <div
            className="border-border flex flex-wrap items-center gap-2 border-b bg-paper-100 px-3 py-2"
            role="toolbar"
            aria-label="Table filters"
          >
            {phaseOptions.map((p) => (
              <Button
                key={p}
                type="button"
                size="sm"
                variant={phaseFilter === p ? "default" : "outline"}
                onClick={() => {
                  setPhaseFilter(p);
                }}
              >
                {p}
              </Button>
            ))}
            <span className="text-muted-foreground mx-1 h-4 w-px select-none" aria-hidden>
              |
            </span>
            {statusOptions.map((s) => (
              <Button
                key={s}
                type="button"
                size="sm"
                variant={statusFilter === s ? "default" : "ghost"}
                onClick={() => {
                  setStatusFilter(s);
                }}
              >
                {s === "All" ? "All statuses" : statusLabel(s as ActionQueueRow["status"])}
              </Button>
            ))}
            <span className="text-muted-foreground mx-1 h-4 w-px select-none" aria-hidden>
              |
            </span>
            {assigneeOptions.map((a) => (
              <Button
                key={a}
                type="button"
                size="sm"
                variant={assigneeFilter === a ? "default" : "outline"}
                onClick={() => {
                  setAssigneeFilter(a);
                }}
              >
                {a === "All" ? "All assignees" : a}
              </Button>
            ))}
          </div>
          <Table className="min-w-full" data-testid="phase-tracking-table">
            <TableHeader>
              {table.getHeaderGroups().map((hg) => (
                <TableRow key={hg.id}>
                  {hg.headers.map((header) => {
                    const sort = header.column.getIsSorted();
                    return (
                      <TableHead
                        key={header.id}
                        className="text-ink-800"
                        aria-sort={
                          !header.column.getCanSort()
                            ? undefined
                            : sort === "asc"
                              ? "ascending"
                              : sort === "desc"
                                ? "descending"
                                : "none"
                        }
                      >
                        {header.isPlaceholder ? null : (
                          <Button
                            type="button"
                            variant="ghost"
                            className={cn(
                              "inline-flex h-auto w-full min-w-0 items-center justify-start gap-1 px-1 py-0.5 text-left font-medium",
                              "text-ink-800 hover:text-ink-950",
                              header.column.getCanSort() ? "cursor-pointer" : "cursor-default",
                            )}
                            onClick={header.column.getToggleSortingHandler()}
                            disabled={!header.column.getCanSort()}
                          >
                            {flexRender(header.column.columnDef.header, header.getContext())}
                            {header.column.getCanSort() ? (
                              <span className="text-muted-foreground text-xs" aria-hidden>
                                {sort === "asc" ? "▲" : sort === "desc" ? "▼" : "◇"}
                              </span>
                            ) : null}
                          </Button>
                        )}
                      </TableHead>
                    );
                  })}
                </TableRow>
              ))}
            </TableHeader>
            <TableBody>
              {table.getRowModel().rows.length === 0 ? (
                <TableRow>
                  <TableCell
                    colSpan={columns.length}
                    className="text-center text-muted-foreground h-24"
                  >
                    No items match the current filters.
                  </TableCell>
                </TableRow>
              ) : (
                table.getRowModel().rows.map((row) => {
                  const isSelected = row.original.id === selectedId;
                  return (
                    <TableRow
                      key={row.id}
                      className={cn("cursor-pointer", isSelected && "bg-paper-200")}
                      data-state={isSelected ? "selected" : undefined}
                      onClick={() => {
                        setSelectedId(row.original.id);
                      }}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" || e.key === " ") {
                          e.preventDefault();
                          setSelectedId(row.original.id);
                        }
                      }}
                      tabIndex={0}
                      aria-selected={isSelected}
                    >
                      {row.getVisibleCells().map((cell) => (
                        <TableCell key={cell.id}>
                          {flexRender(cell.column.columnDef.cell, cell.getContext())}
                        </TableCell>
                      ))}
                    </TableRow>
                  );
                })
              )}
            </TableBody>
          </Table>
        </div>
        <aside
          className="border-border bg-card w-full shrink-0 rounded-lg border p-4 lg:max-w-md xl:max-w-lg"
          aria-label="Action queue item detail"
        >
          <div className="sr-only" role="status" aria-live="polite">
            {liveDetail}
          </div>
          {selectedRow ? (
            <div className="flex flex-col gap-3">
              <h2 className="text-foreground text-base font-semibold">{selectedRow.title}</h2>
              <p className="text-ink-700 text-sm leading-relaxed">{selectedRow.summary}</p>
              <dl className="text-body text-ink-800 grid grid-cols-2 gap-x-2 gap-y-1 text-sm">
                <dt className="text-muted-foreground">Phase</dt>
                <dd>{selectedRow.phase}</dd>
                <dt className="text-muted-foreground">Assignee</dt>
                <dd>{selectedRow.assignee}</dd>
                <dt className="text-muted-foreground">Due</dt>
                <dd className="tabular-nums">{selectedRow.due}</dd>
                <dt className="text-muted-foreground">Priority</dt>
                <dd className="tabular-nums">{selectedRow.priority}</dd>
              </dl>
              <EvidencePanel
                id="phase-tracking-evidence"
                visible
                retrievalPhase={selectedRow.retrievalPhase}
                metadata={selectedRow.metadata}
                state={agentDegraded ? "degraded" : "loaded"}
                bodyText={selectedRow.bodyText}
                evidenceSpan={selectedRow.evidenceSpan}
                variant="compact"
              />
              <p className="text-muted-foreground text-xs">
                Resolution / claim / defer actions wire with Action Queue API in a follow-up.
              </p>
            </div>
          ) : (
            <p className="text-muted-foreground text-sm">
              Select a row to view evidence and context.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
