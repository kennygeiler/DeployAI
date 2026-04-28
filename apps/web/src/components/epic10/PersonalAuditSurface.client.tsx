"use client";

import * as React from "react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

type Item = {
  id: string;
  category: string;
  summary: string;
  detail: Record<string, unknown>;
  ref_id: string | null;
  created_at: string;
};

async function fetchPersonalAudit(categoryFilter: string): Promise<
  { ok: true; items: Item[] } | { ok: false; error: string }
> {
  const sp = new URLSearchParams();
  if (categoryFilter.trim()) {
    sp.set("category", categoryFilter.trim());
  }
  const r = await fetch(`/api/bff/personal-audit?${sp.toString()}`, { cache: "no-store" });
  if (!r.ok) {
    return { ok: false, error: await r.text() };
  }
  const j = (await r.json()) as { items: Item[] };
  return { ok: true, items: j.items ?? [] };
}

export function PersonalAuditSurface() {
  const [items, setItems] = React.useState<Item[]>([]);
  const [categoryFilter, setCategoryFilter] = React.useState("");
  const [err, setErr] = React.useState<string | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    (async () => {
      const result = await fetchPersonalAudit(categoryFilter);
      if (cancelled) return;
      if (!result.ok) {
        setErr(result.error);
        return;
      }
      setErr(null);
      setItems(result.items);
    })();
    return () => {
      cancelled = true;
    };
  }, [categoryFilter]);

  const refresh = React.useCallback(() => {
    void (async () => {
      const result = await fetchPersonalAudit(categoryFilter);
      if (!result.ok) {
        setErr(result.error);
        return;
      }
      setErr(null);
      setItems(result.items);
    })();
  }, [categoryFilter]);

  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-display text-ink-950 font-semibold tracking-tight">Personal audit</h1>
        <p className="text-body text-ink-600 mt-1">
          Your strategist actions on this tenant (not the full admin audit log). Epic 10.7.
        </p>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <label className="flex items-center gap-2 text-sm text-ink-800">
          Category (exact)
          <input
            type="text"
            className="rounded-md border border-border bg-paper-100 px-2 py-1 text-sm"
            value={categoryFilter}
            onChange={(e) => {
              setCategoryFilter(e.target.value);
            }}
            placeholder="override_submitted"
          />
        </label>
        <Button type="button" variant="secondary" size="sm" onClick={refresh}>
          Refresh
        </Button>
      </div>
      {err ? (
        <p className="text-sm text-rose-700" role="alert">
          {err}
        </p>
      ) : null}
      <ul className="divide-y divide-border rounded-md border border-border">
        {items.length === 0 ? (
          <li className="text-ink-500 px-3 py-6 text-sm">No activity rows yet.</li>
        ) : (
          items.map((i) => (
            <li key={i.id} className="space-y-1 px-3 py-3 text-sm">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="font-medium text-ink-900">{i.summary}</span>
                <time className="text-ink-500 text-xs" dateTime={i.created_at}>
                  {new Date(i.created_at).toLocaleString()}
                </time>
              </div>
              <p className="text-ink-600 text-xs">
                <span className="font-mono">{i.category}</span>
                {i.ref_id ? ` · ref ${i.ref_id.slice(0, 8)}…` : null}
              </p>
            </li>
          ))
        )}
      </ul>
      <Link
        href="/overrides"
        className="text-evidence-800 text-sm font-medium underline-offset-2 hover:underline"
      >
        Override history
      </Link>
    </div>
  );
}
