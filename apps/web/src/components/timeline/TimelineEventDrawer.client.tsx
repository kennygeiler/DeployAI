"use client";

import * as React from "react";

import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

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

export function TimelineEventDrawer({
  event,
  open,
  onClose,
}: {
  event: LedgerEvent | null;
  open: boolean;
  onClose: () => void;
}) {
  return (
    <Sheet
      open={open}
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
    >
      <SheetContent
        side="right"
        className="w-full sm:max-w-lg"
        aria-label="Timeline event detail"
        data-testid="timeline-event-drawer"
      >
        {event ? (
          <>
            <SheetHeader>
              <SheetTitle>{event.summary}</SheetTitle>
              <SheetDescription>
                {formatOccurredAt(event.occurred_at)} — {event.source_kind}
              </SheetDescription>
            </SheetHeader>
            <div className="space-y-4 overflow-y-auto px-4 pb-4 text-sm">
              <section className="space-y-1">
                <h3 className="text-ink-700 text-xs font-semibold uppercase">Actor</h3>
                <p className="text-ink-700">
                  {event.actor_kind}
                  {event.actor_id ? <span className="font-mono"> {event.actor_id}</span> : null}
                </p>
              </section>

              {event.source_ref ? (
                <section className="space-y-1">
                  <h3 className="text-ink-700 text-xs font-semibold uppercase">Source ref</h3>
                  <p className="text-ink-700 font-mono break-all">{event.source_ref}</p>
                </section>
              ) : null}

              <section className="space-y-1">
                <h3 className="text-ink-700 text-xs font-semibold uppercase">Detail</h3>
                <pre
                  className="border-border bg-ink-50 text-ink-700 max-h-64 overflow-auto rounded-md border p-2 text-xs"
                  data-testid="timeline-event-detail"
                >
                  {JSON.stringify(event.detail, null, 2)}
                </pre>
              </section>

              <section className="space-y-1">
                <h3 className="text-ink-700 text-xs font-semibold uppercase">
                  Caused by ({event.caused_by_ids.length})
                </h3>
                {event.caused_by_ids.length === 0 ? (
                  <p className="text-ink-500 text-xs">No upstream causes.</p>
                ) : (
                  <ul className="space-y-1">
                    {event.caused_by_ids.map((id) => (
                      <li key={id} className="text-ink-700 font-mono text-xs break-all">
                        {id}
                      </li>
                    ))}
                  </ul>
                )}
              </section>

              <section className="space-y-1">
                <h3 className="text-ink-700 text-xs font-semibold uppercase">
                  Affects ({event.affects.length})
                </h3>
                {event.affects.length === 0 ? (
                  <p className="text-ink-500 text-xs">No matrix entities affected.</p>
                ) : (
                  <ul className="space-y-1">
                    {event.affects.map((a) => (
                      <li key={`${a.entity_kind}:${a.entity_id}`} className="text-ink-700 text-xs">
                        <span className="bg-ink-100 mr-2 rounded px-1.5 py-0.5 font-mono uppercase">
                          {a.entity_kind}
                        </span>
                        <span className="font-mono break-all">{a.entity_id}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>
          </>
        ) : null}
      </SheetContent>
    </Sheet>
  );
}
