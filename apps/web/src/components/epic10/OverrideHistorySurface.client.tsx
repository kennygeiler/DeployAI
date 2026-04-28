"use client";

import * as React from "react";
import Link from "next/link";
import {
  createColumnHelper,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";

import { OverrideComposer, type OverrideEvidenceOption } from "@deployai/shared-ui";

type Row = {
  override_event_id: string;
  occurred_at: string;
  learning_id: string;
  learning_belief: string;
  reason: string;
  overriding_evidence_count: number;
  overriding_evidence_event_ids: string[];
  author_actor_id: string;
};

export function OverrideHistorySurface() {
  const [rows, setRows] = React.useState<Row[]>([]);
  const [mineOnly, setMineOnly] = React.useState(false);
  const [from, setFrom] = React.useState("");
  const [to, setTo] = React.useState("");
  const [loadErr, setLoadErr] = React.useState<string | null>(null);
  const [evidenceOptions, setEvidenceOptions] = React.useState<OverrideEvidenceOption[]>([]);

  const load = React.useCallback(async () => {
    setLoadErr(null);
    const sp = new URLSearchParams();
    if (mineOnly) {
      sp.set("mineOnly", "1");
    }
    if (from.trim()) {
      sp.set("from", new Date(from).toISOString());
    }
    if (to.trim()) {
      sp.set("to", new Date(to).toISOString());
    }
    const r = await fetch(`/api/bff/overrides?${sp.toString()}`, { cache: "no-store" });
    if (!r.ok) {
      setLoadErr(await r.text());
      return;
    }
    const j = (await r.json()) as { items: Row[] };
    setRows(j.items ?? []);
  }, [mineOnly, from, to]);

  React.useEffect(() => {
    void load();
  }, [load]);

  React.useEffect(() => {
    void fetch("/api/bff/strategist-memory-search?q=.")
      .then((r) => r.json())
      .then((j: { hits?: { id: string; label: string }[] }) => {
        const h = j.hits ?? [];
        setEvidenceOptions(
          h.length > 0
            ? h.map((x) => ({ id: x.id, label: x.label }))
            : [{ id: "00000000-0000-7000-8000-000000000001", label: "Demo evidence (configure digest)" }],
        );
      })
      .catch(() => {
        setEvidenceOptions([
          { id: "00000000-0000-7000-8000-000000000001", label: "Demo evidence (search unavailable)" },
        ]);
      });
  }, []);

  const col = createColumnHelper<Row>();
  const columns = React.useMemo(
    () => [
      col.accessor("occurred_at", {
        header: "When",
        cell: (c) => new Date(c.getValue()).toLocaleString(),
      }),
      col.accessor("learning_belief", { header: "Learning", cell: (c) => c.getValue() || "—" }),
      col.accessor("reason", {
        header: "Reason",
        cell: (c) => {
          const t = c.getValue();
          return t.length > 120 ? `${t.slice(0, 117)}…` : t;
        },
      }),
      col.accessor("overriding_evidence_count", { header: "# Evid." }),
      col.accessor("author_actor_id", {
        header: "Author",
        cell: (c) => c.getValue().slice(0, 8),
      }),
      col.display({
        id: "evidence",
        header: "Evidence",
        cell: (ctx) => {
          const first = ctx.row.original.overriding_evidence_event_ids[0];
          if (!first) {
            return "—";
          }
          return (
            <Link
              className="text-evidence-800 font-medium underline-offset-2 hover:underline"
              href={`/evidence/${encodeURIComponent(first)}`}
            >
              Open
            </Link>
          );
        },
      }),
    ],
    [col],
  );

  const table = useReactTable({
    data: rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="max-w-6xl space-y-8">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Override history</h1>
        <p className="text-body text-ink-600 mt-1">
          Durable overrides from canonical memory (Epic 10). Filter by scope and open linked evidence.
        </p>
      </div>

      <section aria-labelledby="ov-compose-h" className="space-y-3">
        <h2 id="ov-compose-h" className="text-lg font-semibold text-ink-900">
          New override
        </h2>
        <OverrideComposer
          evidenceOptions={evidenceOptions}
          withLearningId
          withPrivateAnnotation
          onSubmit={async (payload) => {
            const r = await fetch("/api/bff/overrides", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                learning_id: payload.learningId,
                what_changed: payload.whatChanged,
                why: payload.why,
                evidence_event_ids: payload.evidenceNodeIds,
                private_annotation: payload.privateAnnotation,
              }),
            });
            if (!r.ok) {
              throw new Error(await r.text());
            }
            await load();
          }}
        />
      </section>

      <section aria-labelledby="ov-table-h" className="space-y-3">
        <h2 id="ov-table-h" className="text-lg font-semibold text-ink-900">
          History
        </h2>
        <div className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink-700">From</span>
            <input
              type="datetime-local"
              className="rounded-md border border-border bg-paper-100 px-2 py-1 text-sm"
              value={from}
              onChange={(e) => {
                setFrom(e.target.value);
              }}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-ink-700">To</span>
            <input
              type="datetime-local"
              className="rounded-md border border-border bg-paper-100 px-2 py-1 text-sm"
              value={to}
              onChange={(e) => {
                setTo(e.target.value);
              }}
            />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={mineOnly}
              onChange={(e) => {
                setMineOnly(e.target.checked);
              }}
              className="size-4 accent-evidence-700"
            />
            Mine only
          </label>
          <button
            type="button"
            className="rounded-md border border-border bg-paper-100 px-3 py-1.5 text-sm font-medium hover:bg-paper-200"
            onClick={() => void load()}
          >
            Apply filters
          </button>
        </div>
        {loadErr ? (
          <p className="text-sm text-rose-700" role="alert">
            {loadErr}
          </p>
        ) : null}
        <div className="overflow-x-auto rounded-md border border-border">
          <table className="w-full min-w-[640px] text-left text-sm">
            <thead className="bg-muted/40 text-ink-800">
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
                  <td
                    colSpan={table.getHeaderGroups()[0]?.headers.length ?? 1}
                    className="text-ink-500 px-3 py-6"
                  >
                    No overrides yet (or control plane not configured for this tenant).
                  </td>
                </tr>
              ) : (
                table.getRowModel().rows.map((row) => (
                  <tr key={row.id} className="border-t border-border">
                    {row.getVisibleCells().map((cell) => (
                      <td key={cell.id} className="text-ink-900 px-3 py-2 align-top">
                        {flexRender(cell.column.columnDef.cell, cell.getContext())}
                      </td>
                    ))}
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <Link
        href="/digest"
        className="text-evidence-800 inline-block text-sm font-medium underline-offset-2 hover:underline"
      >
        Back to Morning digest
      </Link>
    </div>
  );
}
