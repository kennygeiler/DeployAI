"use client";

import * as React from "react";

import type { MatrixSnapshot } from "@/lib/internal/matrix-snapshot-cp";

type DiffRow = { field: string; before: string; after: string };

function isoToYyyyMmDdMinusOneDay(iso: string): string | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  d.setUTCDate(d.getUTCDate() - 1);
  return d.toISOString().slice(0, 10);
}

function stringify(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "string") return value;
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function diffNode(before: Record<string, unknown>, after: Record<string, unknown>): DiffRow[] {
  const keys = new Set<string>([...Object.keys(before), ...Object.keys(after)]);
  const rows: DiffRow[] = [];
  for (const key of Array.from(keys).sort()) {
    const b = stringify(before[key]);
    const a = stringify(after[key]);
    if (b !== a) {
      rows.push({ field: key, before: b, after: a });
    }
  }
  return rows;
}

export type LedgerDiffViewProps = {
  engagementId: string;
  nodeId: string;
  occurredAt: string;
  currentNodeFields: { title: string; node_type: string; attributes: Record<string, unknown> };
};

/**
 * G2.c — for a `matrix_node_updated` ledger event, render the field-level
 * diff between the matrix snapshot from the day BEFORE the event and the
 * current node state. Returns null when no prior snapshot exists or the
 * node didn't exist in that snapshot.
 */
export function LedgerDiffView({
  engagementId,
  nodeId,
  occurredAt,
  currentNodeFields,
}: LedgerDiffViewProps): React.ReactElement | null {
  const [diff, setDiff] = React.useState<DiffRow[] | null>(null);
  const [loaded, setLoaded] = React.useState(false);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      const at = isoToYyyyMmDdMinusOneDay(occurredAt);
      if (!at) {
        if (!cancelled) {
          setDiff(null);
          setLoaded(true);
        }
        return;
      }
      try {
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/matrix-snapshot?at=${encodeURIComponent(at)}`,
          { cache: "no-store" },
        );
        if (cancelled) return;
        if (!r.ok) {
          setDiff(null);
          return;
        }
        const body = (await r.json()) as { snapshot?: MatrixSnapshot };
        const snap = body.snapshot;
        const prior = snap?.nodes.find((n) => n.id === nodeId) ?? null;
        if (!prior) {
          setDiff(null);
          return;
        }
        const before: Record<string, unknown> = {
          title: prior.title,
          node_type: prior.node_type,
          attributes: prior.attributes ?? {},
        };
        const after: Record<string, unknown> = {
          title: currentNodeFields.title,
          node_type: currentNodeFields.node_type,
          attributes: currentNodeFields.attributes ?? {},
        };
        setDiff(diffNode(before, after));
      } catch {
        if (!cancelled) setDiff(null);
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [
    engagementId,
    nodeId,
    occurredAt,
    currentNodeFields.title,
    currentNodeFields.node_type,
    currentNodeFields.attributes,
  ]);

  if (!loaded) return null;
  if (!diff || diff.length === 0) return null;
  return (
    <div data-testid="ledger-diff-view" className="space-y-2 text-sm">
      <h3 className="text-ink-700 text-xs font-semibold uppercase">Changes since last snapshot</h3>
      <ul className="border-border divide-border divide-y rounded-lg border">
        {diff.map((row) => (
          <li key={row.field} className="px-3 py-2">
            <div className="text-ink-700 text-xs font-semibold">{row.field}</div>
            <div className="mt-1 grid grid-cols-2 gap-2 font-mono text-xs">
              <div>
                <span className="text-ink-500">before:</span>{" "}
                <span className="text-ink-800 break-all">{row.before}</span>
              </div>
              <div>
                <span className="text-ink-500">after:</span>{" "}
                <span className="text-ink-800 break-all">{row.after}</span>
              </div>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}
