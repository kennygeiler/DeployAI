"use client";

import * as React from "react";

import { Button } from "@/components/ui/button";
import type { LedgerEvent } from "@/lib/internal/ledger-cp";

const ROW_HEIGHT = 88;
const OVERSCAN = 8;

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

export function TimelineList({
  events,
  onSelect,
  selectedId,
}: {
  events: LedgerEvent[];
  onSelect: (event: LedgerEvent) => void;
  selectedId?: string | null;
}) {
  const containerRef = React.useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = React.useState(0);
  const [viewportHeight, setViewportHeight] = React.useState(600);

  React.useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    setViewportHeight(el.clientHeight);
    const onScroll = () => setScrollTop(el.scrollTop);
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, []);

  const total = events.length;
  const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN);
  const visibleCount = Math.ceil(viewportHeight / ROW_HEIGHT) + OVERSCAN * 2;
  const endIdx = Math.min(total, startIdx + visibleCount);
  const visible = events.slice(startIdx, endIdx);
  const topPad = startIdx * ROW_HEIGHT;
  const bottomPad = Math.max(0, (total - endIdx) * ROW_HEIGHT);

  return (
    <div
      ref={containerRef}
      data-testid="timeline-list"
      className="border-border bg-background h-[70vh] flex-1 overflow-y-auto rounded-lg border"
    >
      {total === 0 ? (
        <p className="text-ink-600 p-4 text-sm">
          No events recorded yet. Timeline populates as the team paste-imports emails / meetings or
          as the LLM proposes matrix changes.
        </p>
      ) : (
        <ul aria-label="Timeline events" className="divide-border divide-y">
          {topPad > 0 ? <li aria-hidden style={{ height: topPad }} /> : null}
          {visible.map((ev) => {
            const isSelected = selectedId === ev.id;
            return (
              <li key={ev.id} style={{ height: ROW_HEIGHT }}>
                <Button
                  variant="ghost"
                  onClick={() => onSelect(ev)}
                  data-testid={`timeline-row-${ev.id}`}
                  aria-pressed={isSelected}
                  className={
                    "flex h-full w-full flex-col items-start gap-1 rounded-none px-4 py-2 text-left whitespace-normal " +
                    (isSelected ? "bg-ink-100" : "")
                  }
                >
                  <div className="flex w-full items-center justify-between gap-3">
                    <span className="text-ink-700 text-xs">{formatOccurredAt(ev.occurred_at)}</span>
                    <span className="bg-ink-100 text-ink-800 rounded px-1.5 py-0.5 font-mono text-[10px] uppercase">
                      {ev.source_kind}
                    </span>
                  </div>
                  <p className="text-ink-700 line-clamp-2 text-sm">{ev.summary}</p>
                  <div className="text-ink-500 flex w-full items-center gap-2 text-xs">
                    <span>{ev.actor_kind}</span>
                    {ev.actor_id ? <span className="font-mono">{ev.actor_id}</span> : null}
                    {ev.affects.length > 0 ? (
                      <span className="ml-auto">{ev.affects.length} affected</span>
                    ) : null}
                  </div>
                </Button>
              </li>
            );
          })}
          {bottomPad > 0 ? <li aria-hidden style={{ height: bottomPad }} /> : null}
        </ul>
      )}
    </div>
  );
}
