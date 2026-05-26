"use client";

import * as React from "react";

import { toIsoDay, type DateRange } from "@/lib/bff/temporal-filter";

type Props = {
  events: { timestamp: string }[];
  range: DateRange;
  height?: number;
  label?: string;
};

const DAY_MS = 24 * 60 * 60 * 1000;

function startOfUtcDay(ms: number): number {
  const d = new Date(ms);
  return Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate());
}

/**
 * Pure SVG sparkline. Bins events by UTC day across the active range and
 * renders one bar per day. Empty range = nothing-to-show placeholder; never
 * throws on 0 events.
 */
export function DensityStrip({ events, range, height = 24, label }: Props) {
  const { bins, fromIso, toIso } = React.useMemo(() => {
    const stamps: number[] = [];
    for (const ev of events) {
      const ms = new Date(ev.timestamp).getTime();
      if (!Number.isNaN(ms)) stamps.push(ms);
    }
    if (stamps.length === 0 && (!range.from || !range.to)) {
      return { bins: [] as number[], fromIso: null, toIso: null };
    }
    const fromMs = range.from
      ? startOfUtcDay(range.from.getTime())
      : startOfUtcDay(Math.min(...stamps));
    const toMs = range.to ? startOfUtcDay(range.to.getTime()) : startOfUtcDay(Math.max(...stamps));
    const dayCount = Math.max(1, Math.floor((toMs - fromMs) / DAY_MS) + 1);
    const counts = new Array<number>(dayCount).fill(0);
    for (const ms of stamps) {
      const dayStart = startOfUtcDay(ms);
      const idx = Math.floor((dayStart - fromMs) / DAY_MS);
      if (idx >= 0 && idx < dayCount) counts[idx]! += 1;
    }
    return {
      bins: counts,
      fromIso: toIsoDay(new Date(fromMs)),
      toIso: toIsoDay(new Date(toMs)),
    };
  }, [events, range.from, range.to]);

  if (bins.length === 0) {
    return (
      <div
        className="text-ink-500 border-border bg-paper-50 rounded-md border px-2 py-1 text-[10px]"
        data-testid="density-strip-empty"
        aria-label={label ?? "Event density (no range)"}
      >
        No active range
      </div>
    );
  }

  const totalEvents = bins.reduce((acc, n) => acc + n, 0);
  const max = bins.reduce((acc, n) => (n > acc ? n : acc), 0);
  const width = 200;
  const barWidth = width / bins.length;
  const ariaLabel =
    label ??
    (totalEvents === 0
      ? `Event density: 0 events from ${fromIso} to ${toIso}`
      : `Event density: ${totalEvents} events across ${bins.length} days from ${fromIso} to ${toIso}`);

  return (
    <svg
      role="img"
      aria-label={ariaLabel}
      data-testid="density-strip"
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="text-evidence-700 block"
    >
      <rect
        x={0}
        y={0}
        width={width}
        height={height}
        className="fill-paper-50 stroke-border"
        strokeWidth={1}
      />
      {max === 0
        ? null
        : bins.map((count, i) => {
            const h = (count / max) * (height - 2);
            if (h <= 0) return null;
            return (
              <rect
                key={i}
                x={i * barWidth + 0.5}
                y={height - 1 - h}
                width={Math.max(0.5, barWidth - 1)}
                height={h}
                className="fill-current"
              />
            );
          })}
    </svg>
  );
}
