"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

/**
 * G2.c — "Audit AI" timeline filter + reject action.
 *
 * Filters the ledger to `actor_kind=agent` rows and renders each with a
 * Reject button that POSTs to `/audit-decision`. Distinct from the larger
 * `TimelineView` (timeline page) — this is the focused audit-the-AI surface
 * the owner asked for in post-F-polish §7.C.
 */

type Filter = "all" | "agent";

function formatOccurredAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function EngagementTimeline({ engagementId }: { engagementId: string }): React.ReactElement {
  const [events, setEvents] = React.useState<LedgerEvent[]>([]);
  const [filter, setFilter] = React.useState<Filter>("all");
  const [loading, setLoading] = React.useState(true);
  const [err, setErr] = React.useState<string | null>(null);
  const [rejectedIds, setRejectedIds] = React.useState<Set<string>>(new Set());
  const [busyId, setBusyId] = React.useState<string | null>(null);

  const reload = React.useCallback(async () => {
    setLoading(true);
    try {
      const qs = new URLSearchParams({ limit: "200" });
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/ledger?${qs.toString()}`,
        { cache: "no-store" },
      );
      if (!r.ok) {
        setErr(await readStrategistBffErrorDescription(r));
        setEvents([]);
        return;
      }
      const body = (await r.json()) as { events?: LedgerEvent[] };
      setErr(null);
      setEvents(Array.isArray(body.events) ? body.events : []);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Could not load timeline.");
    } finally {
      setLoading(false);
    }
  }, [engagementId]);

  React.useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        await reload();
      } finally {
        if (cancelled) {
          // no-op; teardown ignores result
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [reload]);

  const visible = React.useMemo(() => {
    if (filter === "agent") {
      return events.filter((e) => e.actor_kind.startsWith("agent"));
    }
    return events;
  }, [events, filter]);

  const handleReject = async (event: LedgerEvent) => {
    setBusyId(event.id);
    try {
      const r = await fetch(
        `/api/bff/engagements/${encodeURIComponent(engagementId)}/audit-decision`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ event_id: event.id, reason: null }),
          cache: "no-store",
        },
      );
      if (!r.ok) {
        setErr(await readStrategistBffErrorDescription(r));
        return;
      }
      setErr(null);
      setRejectedIds((prev) => new Set(prev).add(event.id));
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Reject failed.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section
      aria-labelledby="audit-ai-timeline-heading"
      className="space-y-3"
      data-testid="engagement-timeline-audit"
    >
      <header className="flex items-center justify-between gap-3">
        <h2 id="audit-ai-timeline-heading" className="text-ink-800 text-sm font-semibold">
          Timeline
        </h2>
        <div role="group" aria-label="Actor filter" className="flex gap-1">
          <Button
            variant={filter === "all" ? "default" : "ghost"}
            size="sm"
            onClick={() => setFilter("all")}
            aria-pressed={filter === "all"}
          >
            All
          </Button>
          <Button
            variant={filter === "agent" ? "default" : "ghost"}
            size="sm"
            onClick={() => setFilter("agent")}
            aria-pressed={filter === "agent"}
            data-testid="audit-ai-chip"
          >
            Audit AI
          </Button>
        </div>
      </header>
      {err ? (
        <p role="alert" className="text-error-700 text-sm">
          {err}
        </p>
      ) : null}
      {loading ? (
        <p className="text-ink-600 text-sm">Loading…</p>
      ) : visible.length === 0 ? (
        <p className="text-ink-600 text-sm">No events.</p>
      ) : (
        <ul className="border-border divide-border divide-y rounded-lg border text-sm">
          {visible.map((ev) => {
            const isAgent = ev.actor_kind.startsWith("agent");
            const rejected = rejectedIds.has(ev.id);
            return (
              <li key={ev.id} className="space-y-1 px-3 py-2">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-ink-700 text-xs">{formatOccurredAt(ev.occurred_at)}</span>
                  <span className="bg-ink-100 text-ink-800 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase">
                    {ev.source_kind}
                  </span>
                </div>
                <p className="text-ink-700 whitespace-pre-line">{ev.summary}</p>
                {isAgent ? (
                  <div className="flex items-center justify-end">
                    <Button
                      variant="ghost"
                      size="sm"
                      disabled={busyId === ev.id || rejected}
                      onClick={() => handleReject(ev)}
                      data-testid={`audit-reject-${ev.id}`}
                    >
                      {rejected ? "Rejected" : busyId === ev.id ? "Rejecting…" : "Reject"}
                    </Button>
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
