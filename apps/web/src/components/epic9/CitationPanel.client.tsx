"use client";

import * as React from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import { readStrategistBffErrorDescription } from "@/lib/bff/read-strategist-bff-error";

type CitationEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  source_ref: string | null;
  summary: string;
};

function formatOccurredAt(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) {
    return iso;
  }
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function CitationPanel({
  engagementId,
  ids,
  title,
  open,
  onClose,
}: {
  engagementId: string;
  ids: string[];
  title: string;
  open: boolean;
  onClose: () => void;
}) {
  const [events, setEvents] = React.useState<CitationEvent[]>([]);
  const [loading, setLoading] = React.useState(false);
  const [err, setErr] = React.useState<string | null>(null);

  const idsKey = ids.join(",");

  React.useEffect(() => {
    if (!open) {
      return;
    }
    let cancelled = false;
    void (async () => {
      if (ids.length === 0) {
        if (!cancelled) {
          setEvents([]);
          setErr(null);
          setLoading(false);
        }
        return;
      }
      setLoading(true);
      setErr(null);
      try {
        const url =
          `/api/bff/engagements/${encodeURIComponent(engagementId)}/events` +
          `?ids=${encodeURIComponent(idsKey)}`;
        const r = await fetch(url, { cache: "no-store" });
        if (cancelled) {
          return;
        }
        if (!r.ok) {
          setErr(await readStrategistBffErrorDescription(r));
          setEvents([]);
          return;
        }
        const body = (await r.json()) as { events?: CitationEvent[] };
        setEvents(Array.isArray(body.events) ? body.events : []);
      } catch (e) {
        // Wrap effect-fired fetches so AbortError / teardown leaks don't
        // surface as unhandled rejections (AGENTS.md §6).
        if (!cancelled) {
          setErr(e instanceof Error ? e.message : "Could not load source events.");
          setEvents([]);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [open, engagementId, idsKey, ids.length]);

  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onClose();
        }
      }}
    >
      <SheetContent
        side="right"
        className="w-full sm:max-w-md"
        aria-label="Source events"
        data-testid="citation-panel"
      >
        <SheetHeader>
          <SheetTitle>{title}</SheetTitle>
          <SheetDescription>
            {ids.length === 0
              ? "No source events cited."
              : `${ids.length} cited event${ids.length === 1 ? "" : "s"}.`}
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-3 overflow-y-auto px-4 pb-4">
          {err ? <p className="text-error-700 text-sm">{err}</p> : null}
          {loading ? (
            <p className="text-ink-600 text-sm">Loading…</p>
          ) : ids.length === 0 ? (
            <p className="text-ink-600 text-sm">
              No source events to show — this entity has no evidence cited.
            </p>
          ) : events.length === 0 && !err ? (
            <p className="text-ink-600 text-sm">No source events found.</p>
          ) : (
            <ul className="border-border divide-border divide-y rounded-lg border text-sm">
              {events.map((ev) => (
                <li key={ev.id} className="space-y-1 px-3 py-2">
                  <div className="flex items-center justify-between gap-3">
                    <span className="text-ink-700 text-xs">{formatOccurredAt(ev.occurred_at)}</span>
                    <span className="bg-ink-100 text-ink-800 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase">
                      {ev.event_type}
                    </span>
                  </div>
                  <p className="text-ink-800 whitespace-pre-line">{ev.summary}</p>
                  {ev.source_ref ? (
                    <p className="text-ink-500 font-mono text-xs break-all">{ev.source_ref}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </div>
      </SheetContent>
    </Sheet>
  );
}
