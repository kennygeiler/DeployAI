"use client";

import * as React from "react";

import { TimelineEventDrawer } from "@/components/timeline/TimelineEventDrawer.client";
import {
  TimelineFilters,
  type TimelineFilterValue,
} from "@/components/timeline/TimelineFilters.client";
import { TimelineList } from "@/components/timeline/TimelineList.client";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

const EMPTY_FILTERS: TimelineFilterValue = {
  sourceKinds: [],
  actorId: "",
  from: "",
  to: "",
};

function localToIso(local: string): string | null {
  if (!local) return null;
  const d = new Date(local);
  if (Number.isNaN(d.getTime())) return null;
  return d.toISOString();
}

function buildQuery(filters: TimelineFilterValue): string {
  const qs = new URLSearchParams();
  if (filters.sourceKinds.length > 0) {
    qs.set("source_kind", filters.sourceKinds.join(","));
  }
  if (filters.actorId.trim()) {
    qs.set("actor_id", filters.actorId.trim());
  }
  const from = localToIso(filters.from);
  if (from) qs.set("from", from);
  const to = localToIso(filters.to);
  if (to) qs.set("to", to);
  qs.set("limit", "500");
  return qs.toString();
}

export function TimelineView({ engagementId }: { engagementId: string }) {
  const [filters, setFilters] = React.useState<TimelineFilterValue>(EMPTY_FILTERS);
  const [events, setEvents] = React.useState<LedgerEvent[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [selected, setSelected] = React.useState<LedgerEvent | null>(null);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      if (!cancelled) setLoading(true);
      try {
        const qs = buildQuery(filters);
        const r = await fetch(
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/ledger?${qs}`,
          { cache: "no-store" },
        );
        if (cancelled) return;
        if (!r.ok) {
          setErr(await readStrategistBffErrorDescription(r));
          setEvents([]);
          return;
        }
        const body = (await r.json()) as { events?: LedgerEvent[] };
        setErr(null);
        setEvents(Array.isArray(body.events) ? body.events : []);
      } catch (e) {
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load timeline.");
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [engagementId, filters]);

  return (
    <section
      aria-labelledby="ledger-timeline-heading"
      className="space-y-4 p-4"
      data-testid="timeline-view"
    >
      <header className="space-y-1">
        <h1 id="ledger-timeline-heading" className="text-ink-900 text-lg font-semibold">
          Engagement timeline
        </h1>
        <p className="text-ink-600 text-sm">
          Append-only ledger — every email ingest, meeting webhook, LLM proposal, and matrix change.
        </p>
      </header>

      {err ? (
        <p role="alert" className="text-error-700 text-sm">
          {err}
        </p>
      ) : null}

      <div className="flex flex-col gap-4 md:flex-row">
        <TimelineFilters value={filters} onChange={setFilters} />
        <div className="min-w-0 flex-1">
          {loading ? (
            <p className="text-ink-600 text-sm" data-testid="timeline-loading">
              Loading…
            </p>
          ) : (
            <TimelineList
              events={events}
              onSelect={setSelected}
              selectedId={selected?.id ?? null}
            />
          )}
        </div>
      </div>

      <TimelineEventDrawer
        event={selected}
        open={selected !== null}
        onClose={() => setSelected(null)}
      />
    </section>
  );
}
